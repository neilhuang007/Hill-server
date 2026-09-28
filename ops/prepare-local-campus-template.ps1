param([string]$Runtime = '')
$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Runtime) { $Runtime = Join-Path $RepositoryRoot 'runtime\server' }
$Runtime = [IO.Path]::GetFullPath($Runtime)
$Manifest = @{}
foreach ($Line in Get-Content -LiteralPath (Join-Path $RepositoryRoot 'server-assets\campus-template.env')) {
    if ($Line -match '^(PEOPLE_TEMPLATE_[A-Z0-9_]+)="([^"]+)"$') { $Manifest[$Matches[1]] = $Matches[2] }
}
$Archive = Join-Path $RepositoryRoot "runtime\assets\campus\$($Manifest.PEOPLE_TEMPLATE_ARCHIVE_NAME)"
if (-not (Test-Path -LiteralPath $Archive)) {
    throw "Missing $Archive. Run ops/package-campus-template.py against the verified campus v19 ZIP first."
}
if ((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Manifest.PEOPLE_TEMPLATE_SHA256) {
    throw 'Campus template archive SHA-256 mismatch.'
}
$RunningPaper = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @('java.exe', 'javaw.exe') -and $_.CommandLine -match '(?i)-jar\s+[^\r\n]*paper\.jar'
}
if ($RunningPaper) { throw 'Stop local Paper before changing its campus template.' }
$Staging = Join-Path $Runtime ("assets\campus-staging-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Staging -Force | Out-Null
& tar -xzf $Archive -C $Staging
if ($LASTEXITCODE -ne 0) { throw "Could not extract the verified template into $Staging" }
$Prepared = Join-Path $Staging $Manifest.PEOPLE_TEMPLATE_ARCHIVE_ROOT
$Regions = @(Get-ChildItem -LiteralPath (Join-Path $Prepared 'region') -Filter 'r.*.*.mca' -File)
if ($Regions.Count -ne [int]$Manifest.PEOPLE_TEMPLATE_REGION_MCA_COUNT -or
    -not (Test-Path -LiteralPath (Join-Path $Prepared 'hill-campus-template.yml')) -or
    (Get-Content -LiteralPath (Join-Path $Prepared '.hill175-people-ready') -Raw).Trim() -ne $Manifest.PEOPLE_TEMPLATE_READY_MARKER) {
    throw "Invalid campus template in $Staging"
}
$TemplateParent = Join-Path $Runtime 'world-templates'
New-Item -ItemType Directory -Path $TemplateParent -Force | Out-Null
$Target = Join-Path $TemplateParent $Manifest.PEOPLE_TEMPLATE_ARCHIVE_ROOT
$Backup = Join-Path $Runtime ("assets\people-template-backup-" + [guid]::NewGuid().ToString('N'))
# Resolve every directory before moving it; only known children of this runtime are valid.
foreach ($Candidate in @($Prepared, $Target, $Backup)) {
    if (-not ([IO.Path]::GetFullPath($Candidate).StartsWith($Runtime + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase))) {
        throw "Refused a path outside the runtime: $Candidate"
    }
}
if (Test-Path -LiteralPath $Target) { Move-Item -LiteralPath $Target -Destination $Backup }
try { Move-Item -LiteralPath $Prepared -Destination $Target }
catch {
    if (Test-Path -LiteralPath $Backup) { Move-Item -LiteralPath $Backup -Destination $Target }
    throw
}
Write-Host "Installed campus v19 template at $Target. Previous template retained at $Backup when present."
