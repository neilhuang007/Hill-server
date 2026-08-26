$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Runtime = Join-Path $Root 'runtime\server'
$Assets = Join-Path $Root 'runtime\assets'
$PaperUrl = 'https://fill-data.papermc.io/v1/objects/a8c9140c3075bd7c04973e9cdc491b21bfe6bad472b674ef932a4ae0fec19629/paper-26.2-119.jar'
$PaperSha256 = 'a8c9140c3075bd7c04973e9cdc491b21bfe6bad472b674ef932a4ae0fec19629'
$AuthUrl = 'https://www.curseforge.com/api/v1/mods/1469713/files/8692252/download'
$AuthSha256 = 'de98674487bcd69593c36a03b1204a7d14ff694f281508d156e53650e31e4630'
$HubArchiveName = 'Hill175-Exhibition-Hub-2026-08-26.zip'
$HubArchiveRoot = 'Hill175 Exhibition Hub 2026-08-26'
$HubSha256 = 'd6ebfc048b5dc3351191182255ce77fe101c373bd6bb8a3330d8fc2672c858de'

Push-Location $Root
try {
    & .\gradlew.bat clean test jar
    New-Item -ItemType Directory -Force -Path $Runtime, $Assets, (Join-Path $Runtime 'plugins') | Out-Null

    $PaperJar = Join-Path $Runtime 'paper.jar'
    if (-not (Test-Path $PaperJar)) {
        Invoke-WebRequest -Uri $PaperUrl -OutFile $PaperJar
    }
    if ((Get-FileHash $PaperJar -Algorithm SHA256).Hash.ToLowerInvariant() -ne $PaperSha256) {
        throw 'Paper SHA-256 checksum mismatch.'
    }

    Copy-Item -LiteralPath 'build\libs\Hill-server-1.0-SNAPSHOT.jar' -Destination (Join-Path $Runtime 'plugins\Hill175.jar') -Force
    Copy-Item -LiteralPath 'server-config\server.properties' -Destination (Join-Path $Runtime 'server.properties') -Force
    Copy-Item -LiteralPath 'server-config\spigot.yml' -Destination (Join-Path $Runtime 'spigot.yml') -Force
    $PluginData = Join-Path $Runtime 'plugins\Hill175'
    New-Item -ItemType Directory -Force -Path $PluginData | Out-Null
    Copy-Item -LiteralPath 'src\main\resources\config.yml' -Destination (Join-Path $PluginData 'config.yml') -Force
    if (Test-Path -LiteralPath 'structure.nbt') {
        Copy-Item -LiteralPath 'structure.nbt' -Destination (Join-Path $Runtime 'structure.nbt') -Force
    }
    Set-Content -LiteralPath (Join-Path $Runtime 'eula.txt') -Value 'eula=true'

    $AuthArchive = Join-Path $Assets 'Small-Medieval-Church-1.0.5.zip'
    if (-not (Test-Path $AuthArchive)) {
        Invoke-WebRequest -Uri $AuthUrl -OutFile $AuthArchive
    }
    if ((Get-FileHash $AuthArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $AuthSha256) {
        throw 'Authentication world SHA-256 checksum mismatch.'
    }

    $AuthTarget = Join-Path $Runtime 'hill_auth'
    $ModernAuthTarget = Join-Path $Runtime 'world\dimensions\minecraft\hill_auth'
    $AuthInstallMarker = Join-Path $Assets '.small-medieval-church-1.0.5-installed'
    if (-not (Test-Path $AuthInstallMarker)) {
        # The local Paper process must be stopped before replacing this immutable scenery world.
        Remove-Item -LiteralPath $AuthTarget -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $ModernAuthTarget -Recurse -Force -ErrorAction SilentlyContinue
        $Extract = Join-Path $Runtime 'auth-extract'
        Expand-Archive -LiteralPath $AuthArchive -DestinationPath $Extract -Force
        $AuthRoot = Join-Path $Extract 'Small Medieval Church 1.0.5'
        if (-not (Test-Path (Join-Path $AuthRoot 'level.dat'))) {
            throw 'Authentication world archive did not contain the expected Small Medieval Church 1.0.5 world root.'
        }
        Remove-Item -LiteralPath (Join-Path $AuthRoot 'playerdata') -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath (Join-Path $AuthRoot 'stats') -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath (Join-Path $AuthRoot 'advancements') -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath (Join-Path $AuthRoot 'uid.dat') -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath (Join-Path $AuthRoot 'session.lock') -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $AuthRoot -Destination $AuthTarget
        Remove-Item -LiteralPath $Extract -Recurse -Force
        New-Item -ItemType File -Force -Path $AuthInstallMarker | Out-Null
    }

    $HubArchive = Join-Path $Assets $HubArchiveName
    if (-not (Test-Path $HubArchive)) {
        & (Join-Path $Root 'scripts\package-user-hub.ps1')
    }
    if ((Get-FileHash $HubArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $HubSha256) {
        throw 'Hub world SHA-256 checksum mismatch.'
    }

    $HubTarget = Join-Path $Runtime 'hill_hub'
    $ModernHubTarget = Join-Path $Runtime 'world\dimensions\minecraft\hill_hub'
    $HubInstallMarker = Join-Path $Assets '.hill175-exhibition-hub-2026-08-26-installed'
    $InstalledHubSha = ''
    if (Test-Path -LiteralPath $HubInstallMarker) {
        $MarkerContent = Get-Content -LiteralPath $HubInstallMarker -Raw
        if ($null -ne $MarkerContent) {
            $InstalledHubSha = ([string]$MarkerContent).Trim()
        }
    }
    if ($InstalledHubSha -ne $HubSha256) {
        $RunningPaper = Get-CimInstance Win32_Process | Where-Object {
            $_.Name -in @('java.exe', 'javaw.exe') -and $_.CommandLine -match '(?i)-jar\s+[^\r\n]*paper\.jar'
        }
        if ($RunningPaper) {
            throw 'Stop the local Paper server before replacing the hub world.'
        }
        Remove-Item -LiteralPath $HubTarget -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $ModernHubTarget -Recurse -Force -ErrorAction SilentlyContinue
        $Extract = Join-Path $Runtime 'hub-extract'
        Expand-Archive -LiteralPath $HubArchive -DestinationPath $Extract -Force
        $HubRoot = Join-Path $Extract $HubArchiveRoot
        if (-not (Test-Path (Join-Path $HubRoot 'level.dat'))) {
            throw "Hub archive did not contain the expected $HubArchiveRoot world root."
        }
        Remove-Item -LiteralPath (Join-Path $HubRoot 'players') -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath (Join-Path $HubRoot 'playerdata') -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath (Join-Path $HubRoot 'stats') -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath (Join-Path $HubRoot 'advancements') -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath (Join-Path $HubRoot 'uid.dat') -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath (Join-Path $HubRoot 'session.lock') -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $HubRoot -Destination $HubTarget
        Remove-Item -LiteralPath $Extract -Recurse -Force
        Set-Content -LiteralPath $HubInstallMarker -Value $HubSha256
    }

    Write-Host "Prepared local runtime at $Runtime"
    Write-Host "Start it with: cd '$Runtime'; java -Xms1G -Xmx2G -jar paper.jar nogui"
} finally {
    Pop-Location
}
