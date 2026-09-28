param(
    [string]$Runtime,
    [string]$Manifest,
    [string]$PrimaryWorldName = 'world',
    [string]$SurvivalWorldName = 'world',
    [string]$SurvivalNetherName = 'world_nether',
    [string]$SurvivalEndName = 'world_the_end'
)

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Runtime) {
    $Runtime = Join-Path $Root 'runtime\server'
}
if (-not $Manifest) {
    $Manifest = Join-Path $Root 'server-assets\survival-worldgen-manifest.tsv'
}

$ExpectedHeader = "load_order`trole`tdimension`tproject_title`tslug`tproject_id`tversion_id`tversion_number`tgame_versions`tloader`tclient_side`tserver_side`tfilename`tsize`tsha512`tsha1`tdownload_url`tlicense_id`tlicense_url`tproject_url"
$ExpectedSlugs = @('terralith', 'terratonic', 'structory', 'structory-towers', 'towns-and-towers', 'incendium', 'nullscape')
$ExpectedVersionIds = @('CzijfXJQ', 'cT2AsHrJ', 'OIcllpSf', 'uxUF2h4B', 'E39wx2BN', 'znNBZB6M', 'prWWpjSv')
$OldSurvivalWorldNames = @('hill_survival', 'hill_survival_nether', 'hill_survival_the_end')
$PrimaryDimensionDirNames = @('overworld', 'the_nether', 'the_end')
$PrimaryRootStateDirNames = @('players', 'playerdata', 'data', 'stats', 'advancements')
$PregenRadiusBlocks = 4000

function Fail([string]$Message) {
    throw "survival worldgen prep failed: $Message"
}

function Get-LowerHash([string]$Path, [string]$Algorithm) {
    return (Get-FileHash -LiteralPath $Path -Algorithm $Algorithm).Hash.ToLowerInvariant()
}

function Get-ManifestIdentityHash([string]$Path) {
    $semanticLines = Get-Content -LiteralPath $Path | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_) -and -not $_.StartsWith('#')
    }
    $normalized = (($semanticLines -join "`n") + "`n")
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($normalized)
    $sha512 = [System.Security.Cryptography.SHA512]::Create()
    try {
        return [Convert]::ToHexString($sha512.ComputeHash($bytes)).ToLowerInvariant()
    } finally {
        $sha512.Dispose()
    }
}

function Read-WorldgenManifest([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        Fail "missing manifest: $Path"
    }

    $headerSeen = $false
    $rows = New-Object System.Collections.Generic.List[object]
    $lines = Get-Content -LiteralPath $Path
    foreach ($line in $lines) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('#')) {
            continue
        }
        if (-not $headerSeen) {
            if ($line -ne $ExpectedHeader) {
                Fail 'unexpected manifest header'
            }
            $headerSeen = $true
            continue
        }

        $columns = $line -split "`t"
        if ($columns.Count -ne 20) {
            Fail "manifest row has $($columns.Count) columns instead of 20"
        }
        $rowIndex = $rows.Count
        if ($rowIndex -ge $ExpectedSlugs.Count) {
            Fail 'manifest has more packs than expected'
        }
        $row = [pscustomobject]@{
            load_order = $columns[0]
            role = $columns[1]
            dimension = $columns[2]
            project_title = $columns[3]
            slug = $columns[4]
            project_id = $columns[5]
            version_id = $columns[6]
            version_number = $columns[7]
            game_versions = $columns[8]
            loader = $columns[9]
            client_side = $columns[10]
            server_side = $columns[11]
            filename = $columns[12]
            size = $columns[13]
            sha512 = $columns[14]
            sha1 = $columns[15]
            download_url = $columns[16]
            license_id = $columns[17]
            license_url = $columns[18]
            project_url = $columns[19]
        }

        if ($row.load_order -notmatch '^[0-9]+$' -or [int]$row.load_order -ne ($rowIndex + 1)) {
            Fail "unexpected load order for $($row.slug)"
        }
        if ($row.slug -ne $ExpectedSlugs[$rowIndex]) {
            Fail "unexpected pack slug at load order $($row.load_order): $($row.slug)"
        }
        if ($row.version_id -ne $ExpectedVersionIds[$rowIndex]) {
            Fail "unexpected version id for $($row.slug)"
        }
        if ($row.slug -eq 'tectonic' -or $row.project_title -eq 'Tectonic') {
            Fail 'Tectonic is forbidden in the Hill175 Terralith stack'
        }
        if ($row.loader -ne 'datapack') {
            Fail "$($row.slug) is not pinned as a datapack"
        }
        if (",$(($row.game_versions))," -notlike '*,26.2,*') {
            Fail "$($row.slug) is not pinned for Minecraft 26.2"
        }
        if ($row.client_side -ne 'optional' -or $row.server_side -ne 'required') {
            Fail "$($row.slug) is not server-side datapack content"
        }
        $expectedUrl = "https://cdn.modrinth.com/data/$($row.project_id)/versions/$($row.version_id)/$($row.filename)"
        if ($row.download_url -ne $expectedUrl) {
            Fail "$($row.slug) download URL does not match its Modrinth IDs"
        }
        if ($row.sha512 -notmatch '^[0-9a-f]{128}$') {
            Fail "$($row.slug) has an invalid SHA-512 hash"
        }
        if ($row.sha1 -notmatch '^[0-9a-f]{40}$') {
            Fail "$($row.slug) has an invalid SHA-1 hash"
        }
        if ($row.size -notmatch '^[0-9]+$' -or [int64]$row.size -le 0) {
            Fail "$($row.slug) has an invalid file size"
        }
        $rows.Add($row)
    }

    if (-not $headerSeen) {
        Fail 'manifest header was not found'
    }
    if ($rows.Count -ne $ExpectedSlugs.Count) {
        Fail "manifest pack count $($rows.Count) did not match expected $($ExpectedSlugs.Count)"
    }
    return $rows
}

function Get-RandomPositiveInt64 {
    $bytes = New-Object byte[] 8
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    $bytes[7] = $bytes[7] -band 0x7F
    $value = [BitConverter]::ToInt64($bytes, 0)
    if ($value -le 0) {
        return 1
    }
    return $value
}

function Move-ArchiveTargetIfPresent([string]$RuntimeRoot, [string]$ArchiveDir, [string]$Target, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Target)) {
        return $false
    }
    $resolved = (Resolve-Path -LiteralPath $Target).Path
    $prefix = $RuntimeRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) -or $resolved -eq $RuntimeRoot) {
        Fail "transition target resolved outside runtime: $resolved"
    }
    if ($Label -notmatch '^[A-Za-z0-9_.-]+$') {
        Fail "unsafe archive label: $Label"
    }
    New-Item -ItemType Directory -Force -Path $ArchiveDir | Out-Null
    $destination = Join-Path $ArchiveDir $Label
    if (Test-Path -LiteralPath $destination) {
        Fail "archive destination already exists: $destination"
    }
    Move-Item -LiteralPath $resolved -Destination $destination
    Write-Host "Archived $resolved to $destination"
    return $true
}

function Test-ExcludedArchivedDimension([string]$Name) {
    return ($OldSurvivalWorldNames -contains $Name) -or ($PrimaryDimensionDirNames -contains $Name)
}

function Copy-NonSurvivalCustomDimensions([string]$ArchivedWorld, [string]$NewWorld) {
    $sourceRoot = Join-Path $ArchivedWorld 'dimensions'
    if (-not (Test-Path -LiteralPath $sourceRoot)) {
        return
    }
    $destinationRoot = Join-Path $NewWorld 'dimensions'
    foreach ($namespaceSource in Get-ChildItem -LiteralPath $sourceRoot -Directory -Force) {
        $namespace = $namespaceSource.Name
        $destinationDir = Join-Path $destinationRoot $namespace
        New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null
        foreach ($source in Get-ChildItem -LiteralPath $namespaceSource.FullName -Directory -Force) {
            $name = $source.Name
            if ($namespace -eq 'minecraft' -and (Test-ExcludedArchivedDimension $name)) {
                Write-Host "Left archived primary/survival dimension out of new world: ${namespace}:$name"
                continue
            }
            $destination = Join-Path $destinationDir $name
            if (Test-Path -LiteralPath $destination) {
                Fail "custom dimension restore target already exists: $destination"
            }
            Copy-Item -LiteralPath $source.FullName -Destination $destination -Recurse
            Write-Host "Restored custom dimension ${namespace}:$name into new primary world"
        }
    }
}

function Copy-PrimaryRootStateDirs([string]$ArchivedWorld, [string]$NewWorld) {
    foreach ($stateName in $PrimaryRootStateDirNames) {
        $sourceDir = Join-Path $ArchivedWorld $stateName
        if (-not (Test-Path -LiteralPath $sourceDir)) {
            continue
        }
        New-Item -ItemType Directory -Force -Path $NewWorld | Out-Null
        $destinationDir = Join-Path $NewWorld $stateName
        if (Test-Path -LiteralPath $destinationDir) {
            Fail "primary root state restore target already exists: $destinationDir"
        }
        Copy-Item -LiteralPath $sourceDir -Destination $destinationDir -Recurse
        Write-Host "Restored primary world root state directory $stateName into new primary world"
    }
}

function Copy-ArchivedPrimaryWorldState([string]$ArchivedWorld, [string]$NewWorld) {
    Copy-NonSurvivalCustomDimensions $ArchivedWorld $NewWorld
    Copy-PrimaryRootStateDirs $ArchivedWorld $NewWorld
}

function Invoke-FirstTransitionArchive([string]$RuntimeRoot, [string]$ArchiveRoot, [string]$StateDir) {
    $timestamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    $archiveDir = Join-Path $ArchiveRoot "primary-trio-transition-$timestamp"
    $moved = $false

    if (Move-ArchiveTargetIfPresent $RuntimeRoot $archiveDir (Join-Path $RuntimeRoot $PrimaryWorldName) $PrimaryWorldName) {
        $moved = $true
    }
    if (Move-ArchiveTargetIfPresent $RuntimeRoot $archiveDir (Join-Path $RuntimeRoot $SurvivalNetherName) $SurvivalNetherName) {
        $moved = $true
    }
    if (Move-ArchiveTargetIfPresent $RuntimeRoot $archiveDir (Join-Path $RuntimeRoot $SurvivalEndName) $SurvivalEndName) {
        $moved = $true
    }

    foreach ($oldName in $OldSurvivalWorldNames) {
        if (Move-ArchiveTargetIfPresent $RuntimeRoot $archiveDir (Join-Path $RuntimeRoot $oldName) $oldName) {
            $moved = $true
        }
    }
    foreach ($oldName in $OldSurvivalWorldNames) {
        $nested = Join-Path $RuntimeRoot (Join-Path $PrimaryWorldName "dimensions\minecraft\$oldName")
        if (Move-ArchiveTargetIfPresent $RuntimeRoot $archiveDir $nested "${PrimaryWorldName}__dimensions__minecraft__$oldName") {
            $moved = $true
        }
    }

    if ($moved) {
        Copy-ArchivedPrimaryWorldState (Join-Path $archiveDir $PrimaryWorldName) (Join-Path $RuntimeRoot $PrimaryWorldName)
        [System.IO.File]::WriteAllText((Join-Path $StateDir 'last-transition-archive.txt'), "$archiveDir`n", [System.Text.UTF8Encoding]::new($false))
    }
}

function Write-SeedIfMissing([string]$SeedFile) {
    if (Test-Path -LiteralPath $SeedFile) {
        $existing = (Get-Content -LiteralPath $SeedFile -Raw).Trim()
        if ($existing -notmatch '^[0-9]+$') {
            Fail "survival seed file is not a positive integer: $SeedFile"
        }
        return
    }
    $seed = Get-RandomPositiveInt64
    [System.IO.File]::WriteAllText($SeedFile, "$seed`n", [System.Text.UTF8Encoding]::new($false))
}

function Write-RuntimeSurvivalConfig([string]$ConfigFile, [string]$Seed) {
    if (-not (Test-Path -LiteralPath $ConfigFile)) {
        Fail "missing Hill175 runtime config: $ConfigFile"
    }
    $content = [System.IO.File]::ReadAllText($ConfigFile)
    $content = [regex]::Replace($content, "(?ms)\r?\n?# BEGIN Hill175 installer-managed survival\r?\n.*?# END Hill175 installer-managed survival\r?\n?", "`r`n")
    if ($content -match '(?m)^survival:\s*$') {
        Fail 'runtime config has an unmanaged top-level survival block; remove it before installer-managed seed injection'
    }
    $output = New-Object System.Collections.Generic.List[string]
    $inWorlds = $false
    $inserted = $false
    foreach ($line in ($content -split '\r?\n')) {
        if ($line -match '^worlds:\s*$') {
            $inWorlds = $true
            $output.Add($line)
            continue
        }
        if ($inWorlds -and $line -match '^[^\s#][^:]*:\s*$') {
            if (-not $inserted) {
                $output.Add("  survival: $SurvivalWorldName")
                $output.Add("  survival-nether: $SurvivalNetherName")
                $output.Add("  survival-end: $SurvivalEndName")
                $inserted = $true
            }
            $inWorlds = $false
            $output.Add($line)
            continue
        }
        if ($inWorlds -and $line -match '^  survival(-nether|-end)?:\s*') {
            continue
        }
        $output.Add($line)
    }
    if ($inWorlds -and -not $inserted) {
        $output.Add("  survival: $SurvivalWorldName")
        $output.Add("  survival-nether: $SurvivalNetherName")
        $output.Add("  survival-end: $SurvivalEndName")
    }
    $trimmed = ($output -join "`r`n").TrimEnd()
    $block = @"
# BEGIN Hill175 installer-managed survival
survival:
  seed: $Seed
  difficulty: NORMAL
  keep-inventory: false
  mob-griefing: true
  pvp: true
# END Hill175 installer-managed survival
"@
    [System.IO.File]::WriteAllText($ConfigFile, "$trimmed`r`n`r`n$block`r`n", [System.Text.UTF8Encoding]::new($false))
}

function Set-ServerProperty([string]$PropertiesFile, [string]$Key, [string]$Value) {
    if (-not (Test-Path -LiteralPath $PropertiesFile)) {
        Fail "missing server.properties: $PropertiesFile"
    }
    $lines = New-Object System.Collections.Generic.List[string]
    $written = $false
    foreach ($line in Get-Content -LiteralPath $PropertiesFile) {
        if ($line.StartsWith("$Key=", [System.StringComparison]::Ordinal)) {
            $lines.Add("$Key=$Value")
            $written = $true
        } else {
            $lines.Add($line)
        }
    }
    if (-not $written) {
        $lines.Add("$Key=$Value")
    }
    [System.IO.File]::WriteAllText($PropertiesFile, (($lines -join "`r`n") + "`r`n"), [System.Text.UTF8Encoding]::new($false))
}

function Write-ServerPropertiesSeed([string]$PropertiesFile, [string]$Seed) {
    Set-ServerProperty $PropertiesFile 'level-name' $PrimaryWorldName
    Set-ServerProperty $PropertiesFile 'level-seed' $Seed
    Set-ServerProperty $PropertiesFile 'generate-structures' 'true'
    Set-ServerProperty $PropertiesFile 'allow-nether' 'true'
    Set-ServerProperty $PropertiesFile 'pvp' 'true'
}

function Write-PrimaryTransitionMarker([string]$Marker, [string]$Seed, [string]$ManifestHash) {
    $content = @"
format=hill175-primary-trio-worldgen-v1
primary_world=$PrimaryWorldName
survival_world=$SurvivalWorldName
survival_nether_world=$SurvivalNetherName
survival_end_world=$SurvivalEndName
seed=$Seed
manifest_sha512=$ManifestHash
"@
    [System.IO.File]::WriteAllText($Marker, "$content`r`n", [System.Text.UTF8Encoding]::new($false))
}

function Test-PrimaryTransitionMarker([string]$Marker, [string]$Seed, [string]$ManifestHash) {
    if (-not (Test-Path -LiteralPath $Marker)) {
        return $false
    }
    $content = Get-Content -LiteralPath $Marker
    $expected = @(
        'format=hill175-primary-trio-worldgen-v1',
        "primary_world=$PrimaryWorldName",
        "survival_world=$SurvivalWorldName",
        "survival_nether_world=$SurvivalNetherName",
        "survival_end_world=$SurvivalEndName",
        "seed=$Seed",
        "manifest_sha512=$ManifestHash"
    )
    foreach ($line in $expected) {
        if ($content -notcontains $line) {
            Fail "primary-trio transition marker mismatch: $line"
        }
    }
    return $true
}

function Stage-WorldgenPackCache($Rows, [string]$CacheDir) {
    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
    foreach ($row in $Rows) {
        $cacheFile = Join-Path $CacheDir $row.filename
        if ((Test-Path -LiteralPath $cacheFile) -and (Get-LowerHash $cacheFile 'SHA512') -ne $row.sha512) {
            Remove-Item -LiteralPath $cacheFile -Force
        }
        if (-not (Test-Path -LiteralPath $cacheFile)) {
            $tmp = "$cacheFile.tmp"
            Invoke-WebRequest -Uri $row.download_url -OutFile $tmp
            if ((Get-LowerHash $tmp 'SHA512') -ne $row.sha512) {
                Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
                Fail "downloaded $($row.filename) failed SHA-512 verification"
            }
            Move-Item -LiteralPath $tmp -Destination $cacheFile -Force
        }
        if ((Get-LowerHash $cacheFile 'SHA512') -ne $row.sha512) {
            Fail "cached $($row.filename) failed SHA-512 verification"
        }
    }
}

function Install-WorldgenPacks($Rows, [string]$DatapacksDir, [string]$CacheDir) {
    New-Item -ItemType Directory -Force -Path $DatapacksDir | Out-Null
    foreach ($row in $Rows) {
        $cacheFile = Join-Path $CacheDir $row.filename
        $targetFile = Join-Path $DatapacksDir $row.filename
        if ((-not (Test-Path -LiteralPath $cacheFile)) -or (Get-LowerHash $cacheFile 'SHA512') -ne $row.sha512) {
            Fail "cached $($row.filename) failed SHA-512 verification"
        }
        if ((-not (Test-Path -LiteralPath $targetFile)) -or (Get-LowerHash $targetFile 'SHA512') -ne $row.sha512) {
            Copy-Item -LiteralPath $cacheFile -Destination $targetFile -Force
        }
        if ((Get-LowerHash $targetFile 'SHA512') -ne $row.sha512) {
            Fail "installed $($row.filename) failed SHA-512 verification"
        }
    }

    $selected = @{}
    foreach ($row in $Rows) {
        $selected[$row.filename] = $true
    }
    foreach ($zip in Get-ChildItem -LiteralPath $DatapacksDir -Filter '*.zip' -File -ErrorAction SilentlyContinue) {
        if (-not $selected.ContainsKey($zip.Name)) {
            Fail "unexpected datapack zip in primary world datapacks folder: $($zip.FullName)"
        }
    }
}

function Write-PregenPlan([string]$Target) {
    $content = @"
Hill175 survival pregen plan
radius_blocks=$PregenRadiusBlocks
primary_world=$PrimaryWorldName
survival_world=$SurvivalWorldName
survival_nether_world=$SurvivalNetherName
survival_end_world=$SurvivalEndName
installer_runs_pregen=false
notes=Run a Paper-compatible pregenerator manually after smoke testing if launch load requires it.
"@
    [System.IO.File]::WriteAllText($Target, "$content`r`n", [System.Text.UTF8Encoding]::new($false))
}

$Runtime = (New-Item -ItemType Directory -Force -Path $Runtime).FullName
$Runtime = (Resolve-Path -LiteralPath $Runtime).Path
$Manifest = (Resolve-Path -LiteralPath $Manifest).Path

$RunningPaper = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @('java.exe', 'javaw.exe') -and $_.CommandLine -match '(?i)-jar\s+[^\r\n]*paper\.jar' -and $_.CommandLine -like "*$Runtime*"
}
if ($RunningPaper) {
    Fail "stop the local Paper server before preparing survival worldgen in $Runtime"
}

$StateDir = Join-Path $Runtime 'assets\survival-worldgen'
$CacheDir = Join-Path $Runtime 'assets\survival-worldgen-cache'
$ArchiveRoot = Join-Path $Runtime 'assets\survival-worldgen-archives'
$PrimaryWorldDir = Join-Path $Runtime $PrimaryWorldName
$DatapacksDir = Join-Path $PrimaryWorldDir 'datapacks'
$SeedFile = Join-Path $StateDir 'survival-seed.txt'
$ManifestMarker = Join-Path $StateDir 'installed-manifest.sha512'
$PrimaryTransitionMarker = Join-Path $StateDir 'primary-trio-managed.env'
$ConfigFile = Join-Path $Runtime 'plugins\Hill175\config.yml'
$ServerPropertiesFile = Join-Path $Runtime 'server.properties'

New-Item -ItemType Directory -Force -Path $StateDir, $CacheDir, $ArchiveRoot | Out-Null
$rows = Read-WorldgenManifest $Manifest
$manifestHash = Get-ManifestIdentityHash $Manifest
$installedHash = ''
if (Test-Path -LiteralPath $ManifestMarker) {
    $installedHash = (Get-Content -LiteralPath $ManifestMarker -Raw).Trim()
}
if ($installedHash -and $installedHash -ne $manifestHash) {
    $installedManifest = Join-Path $StateDir 'installed-manifest.tsv'
    if ((-not (Test-Path -LiteralPath $installedManifest)) -or (Get-ManifestIdentityHash $installedManifest) -ne $manifestHash) {
        Fail 'a different survival worldgen manifest is already installed; do not mutate the long-lived survival world in place'
    }
}

Write-SeedIfMissing $SeedFile
$seed = (Get-Content -LiteralPath $SeedFile -Raw).Trim()
Stage-WorldgenPackCache $rows $CacheDir
if (-not (Test-PrimaryTransitionMarker $PrimaryTransitionMarker $seed $manifestHash)) {
    Invoke-FirstTransitionArchive $Runtime $ArchiveRoot $StateDir
    Write-PrimaryTransitionMarker $PrimaryTransitionMarker $seed $manifestHash
}

New-Item -ItemType Directory -Force -Path $DatapacksDir | Out-Null
Install-WorldgenPacks $rows $DatapacksDir $CacheDir
Write-ServerPropertiesSeed $ServerPropertiesFile $seed
Write-RuntimeSurvivalConfig $ConfigFile $seed
Copy-Item -LiteralPath $Manifest -Destination (Join-Path $StateDir 'installed-manifest.tsv') -Force
[System.IO.File]::WriteAllText($ManifestMarker, "$manifestHash`n", [System.Text.UTF8Encoding]::new($false))
Write-PregenPlan (Join-Path $StateDir 'pregen-plan.txt')

Write-Host "Installed Hill175 survival worldgen datapacks into $DatapacksDir"
