# Prepares a Paper runtime on Windows with development sign-in. Maps are read from
# <Runtime>\world-templates\; third-party programs come from server-assets\server-binaries.env.
[CmdletBinding()]
param(
    # Server folder to prepare. Default: runtime\server in this checkout.
    [string]$Runtime = '',
    # Download cache for Paper, Chunky and (when needed) Java. Default: beside the server folder.
    [string]$Assets = ''
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Runtime) { $Runtime = Join-Path $Root 'runtime\server' }
$Runtime = [IO.Path]::GetFullPath($Runtime)
if (-not $Assets) { $Assets = Join-Path (Split-Path -Parent $Runtime) 'assets' }
$Assets = [IO.Path]::GetFullPath($Assets)

function Read-ServerBinaries([string]$Path) {
    $Formats = @{
        PAPER_URL = '^https://[A-Za-z0-9._~/%+-]+$'
        PAPER_SHA256 = '^[0-9a-f]{64}$'
        JAVA_WINDOWS_X64_URL = '^https://[A-Za-z0-9._~/%+-]+$'
        JAVA_WINDOWS_X64_SHA256 = '^[0-9a-f]{64}$'
        CHUNKY_FILENAME = '^[A-Za-z0-9._-]+\.jar$'
        CHUNKY_URL = '^https://[A-Za-z0-9._~/%+-]+$'
        CHUNKY_SHA512 = '^[0-9a-f]{128}$'
    }
    $Values = @{}
    foreach ($Line in Get-Content -LiteralPath $Path) {
        if ([string]::IsNullOrWhiteSpace($Line) -or $Line.StartsWith('#')) { continue }
        $Name, $Value = $Line -split '=', 2
        if ($Values.ContainsKey($Name)) { throw "Duplicate $Name in $Path" }
        $Values[$Name] = $Value
    }
    foreach ($Name in $Formats.Keys) {
        if ($Values[$Name] -cnotmatch $Formats[$Name]) { throw "Missing or invalid $Name in $Path" }
    }
    return $Values
}

function Get-VerifiedDownload([string]$Url, [string]$Path, [string]$Algorithm, [string]$Expected) {
    if ((Test-Path -LiteralPath $Path -PathType Leaf) -and
            (Get-FileHash -LiteralPath $Path -Algorithm $Algorithm).Hash -eq $Expected) {
        return
    }
    $Partial = "$Path.tmp"
    Invoke-WebRequest -Uri $Url -OutFile $Partial -UseBasicParsing
    if ((Get-FileHash -LiteralPath $Partial -Algorithm $Algorithm).Hash -ne $Expected) {
        Remove-Item -LiteralPath $Partial -Force
        throw "$Algorithm checksum mismatch for $Url"
    }
    Move-Item -LiteralPath $Partial -Destination $Path -Force
}

function Get-JavaMajor([string]$Java) {
    # Java reports its version on stderr; keep that from becoming a terminating error.
    $Previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $Report = (& $Java -version 2>&1 | Out-String) } catch { return 0 } finally { $ErrorActionPreference = $Previous }
    if ($Report -match 'version "(\d+)') { return [int]$Matches[1] }
    return 0
}

# Use a JDK 25+ that is already installed; otherwise fetch the listed one into the cache.
function Resolve-JavaHome([hashtable]$Binaries) {
    $Candidates = @()
    if ($env:JAVA_HOME) { $Candidates += $env:JAVA_HOME }
    $OnPath = Get-Command java.exe -ErrorAction SilentlyContinue
    if ($OnPath) { $Candidates += (Split-Path -Parent (Split-Path -Parent $OnPath.Source)) }
    $Cached = Join-Path $Assets 'java25'
    $Candidates += $Cached
    foreach ($Candidate in $Candidates) {
        $Java = Join-Path $Candidate 'bin\java.exe'
        if ((Test-Path -LiteralPath (Join-Path $Candidate 'bin\javac.exe')) -and (Get-JavaMajor $Java) -ge 25) {
            return $Candidate
        }
    }
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        throw 'Only an x86-64 JDK is listed for download. Install a JDK 25 and set JAVA_HOME first.'
    }
    Write-Host 'No JDK 25 or newer found; downloading the listed Temurin JDK.'
    $Archive = Join-Path $Assets 'java25-windows-x64.zip'
    Get-VerifiedDownload $Binaries.JAVA_WINDOWS_X64_URL $Archive 'SHA256' $Binaries.JAVA_WINDOWS_X64_SHA256
    $Extract = Join-Path $Assets 'java25.extracting'
    Remove-Item -LiteralPath $Extract, $Cached -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -LiteralPath $Archive -DestinationPath $Extract
    $Inner = @(Get-ChildItem -LiteralPath $Extract -Directory)
    if ($Inner.Count -ne 1 -or -not (Test-Path -LiteralPath (Join-Path $Inner[0].FullName 'bin\java.exe'))) {
        throw 'The downloaded JDK archive has an unexpected layout.'
    }
    Move-Item -LiteralPath $Inner[0].FullName -Destination $Cached
    Remove-Item -LiteralPath $Extract -Recurse -Force
    return $Cached
}

# A lobby or hub map is a world save placed directly in its designated folder.
function Test-MapFolder([string]$Folder) {
    if (-not (Test-Path -LiteralPath (Join-Path $Folder 'level.dat') -PathType Leaf)) {
        throw "No level.dat directly inside $Folder. Extract the world save itself there, not a ZIP or a nested folder."
    }
    $Links = @(Get-ChildItem -LiteralPath $Folder -Recurse -Force |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
    if ($Links.Count -or ((Get-Item -LiteralPath $Folder).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Map folders must not contain links: $Folder"
    }
    $Regions = @(Get-ChildItem -LiteralPath $Folder -Recurse -File -Filter 'r.*.mca' |
        Where-Object { $_.Directory.Name -eq 'region' -and $_.Length -ge 8192 })
    if ($Regions.Count -eq 0) { throw "No region data in $Folder" }
}

# Minecraft keeps this file open while the server runs.
$SessionLock = Join-Path $Runtime 'world\session.lock'
if (Test-Path -LiteralPath $SessionLock) {
    try {
        [IO.File]::Open($SessionLock, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None).Dispose()
    } catch [IO.IOException] {
        throw "Paper is running in $Runtime. Stop it before preparing or replacing its files."
    }
}

$Templates = Join-Path $Runtime 'world-templates'
$HubFolder = Join-Path $Templates 'hill_hub'
$LobbyFolder = Join-Path $Templates 'hill_auth'
if (-not (Test-Path -LiteralPath $Templates -PathType Container)) {
    throw "No maps found. Copy the asset packet's world-templates folder to $Templates first (see docs\operations\windows-assets.md)."
}

Push-Location $Root
try {
    & (Join-Path $Root 'ops\prepare-local-campus-template.ps1') -Runtime $Runtime
    if (-not (Test-Path -LiteralPath $HubFolder -PathType Container)) {
        throw "Missing exhibition hub map. Copy the supplied world-templates\hill_hub folder to $HubFolder, or build it from a world save with ops\stage-world-template.ps1."
    }
    Test-MapFolder $HubFolder
    if (Test-Path -LiteralPath $LobbyFolder) {
        Test-MapFolder $LobbyFolder
    } else {
        Write-Host "No lobby map in $LobbyFolder; the plugin keeps an installed lobby or builds its plain one."
    }

    New-Item -ItemType Directory -Force -Path $Runtime, $Assets, (Join-Path $Runtime 'plugins') | Out-Null
    $Binaries = Read-ServerBinaries (Join-Path $Root 'server-assets\server-binaries.env')
    $JavaHome = Resolve-JavaHome $Binaries
    $env:JAVA_HOME = $JavaHome
    $env:Path = (Join-Path $JavaHome 'bin') + [IO.Path]::PathSeparator + $env:Path

    & .\gradlew.bat clean test jar
    if ($LASTEXITCODE -ne 0) { throw 'Plugin build or tests failed.' }

    $PaperAsset = Join-Path $Assets 'paper-pinned.jar'
    Get-VerifiedDownload $Binaries.PAPER_URL $PaperAsset 'SHA256' $Binaries.PAPER_SHA256
    Copy-Item -LiteralPath $PaperAsset -Destination (Join-Path $Runtime 'paper.jar') -Force

    $ChunkyFilename = $Binaries.CHUNKY_FILENAME
    $ChunkyAsset = Join-Path $Assets $ChunkyFilename
    Get-VerifiedDownload $Binaries.CHUNKY_URL $ChunkyAsset 'SHA512' $Binaries.CHUNKY_SHA512

    Copy-Item -LiteralPath 'build\libs\Hill-server-1.0-SNAPSHOT.jar' -Destination (Join-Path $Runtime 'plugins\Hill175.jar') -Force
    foreach ($ExistingChunky in Get-ChildItem -LiteralPath (Join-Path $Runtime 'plugins') -Filter '*chunky*.jar' -File -ErrorAction SilentlyContinue) {
        if ($ExistingChunky.Name -ne $ChunkyFilename) {
            throw "Unexpected Chunky plugin jar already exists: $($ExistingChunky.FullName). Remove it deliberately before installing pinned $ChunkyFilename."
        }
    }
    Copy-Item -LiteralPath $ChunkyAsset -Destination (Join-Path $Runtime "plugins\$ChunkyFilename") -Force
    Copy-Item -LiteralPath 'server-config\server.properties' -Destination (Join-Path $Runtime 'server.properties') -Force
    Copy-Item -LiteralPath 'server-config\spigot.yml' -Destination (Join-Path $Runtime 'spigot.yml') -Force
    $PluginData = Join-Path $Runtime 'plugins\Hill175'
    New-Item -ItemType Directory -Force -Path $PluginData | Out-Null
    Copy-Item -LiteralPath 'src\main\resources\config.yml' -Destination (Join-Path $PluginData 'config.yml') -Force
    Set-Content -LiteralPath (Join-Path $Runtime 'eula.txt') -Value 'eula=true'

    & (Join-Path $Root 'ops\prepare-local-survival-worldgen.ps1') `
        -Runtime $Runtime `
        -Manifest (Join-Path $Root 'server-assets\survival-worldgen-manifest.tsv')

    Write-Host "Prepared local runtime at $Runtime"
    Write-Host 'Paper imports the lobby and hub maps from world-templates\ when it starts.'
    Write-Host "Start it with: cd '$Runtime'; & '$(Join-Path $JavaHome 'bin\java.exe')' -Xms1G -Xmx2G -jar paper.jar nogui"
} finally {
    Pop-Location
}
