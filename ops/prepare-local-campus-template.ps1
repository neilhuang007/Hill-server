param([string]$Runtime = '')
$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Runtime) { $Runtime = Join-Path $RepositoryRoot 'runtime\server' }
$Runtime = [IO.Path]::GetFullPath($Runtime)
$Target = Join-Path $Runtime 'world-templates\hill_people_template'
if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
    throw "Extract the supplied campus folder to $Target before preparing the runtime."
}
if ((Get-Item -LiteralPath $Target).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'The campus template must be a regular directory, not a link.'
}
if (Test-Path -LiteralPath (Join-Path $Target 'dimensions')) {
    throw 'The campus folder must contain region\ directly, not a nested dimensions\ directory.'
}
foreach ($Name in @('region', 'poi')) {
    $Folder = Join-Path $Target $Name
    if ($Name -eq 'poi' -and -not (Test-Path -LiteralPath $Folder)) { continue }
    if (-not (Test-Path -LiteralPath $Folder -PathType Container)) { throw "Missing $Folder" }
    if ((Get-Item -LiteralPath $Folder).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "The template's $Name directory must not be a link."
    }
    $Files = @(Get-ChildItem -LiteralPath $Folder | Where-Object Name -Match '^r\.-?\d+\.-?\d+\.mca$')
    if ($Name -eq 'region' -and $Files.Count -eq 0) { throw "No region files in $Folder" }
    foreach ($File in $Files) {
        if ($File.PSIsContainer -or $File.Length -lt 8192 -or ($File.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Invalid or truncated Anvil file: $($File.FullName)"
        }
    }
}
$Marker = Join-Path $Target '.hill175-people-ready'
if ((Test-Path -LiteralPath $Marker) -and (Get-Content -LiteralPath $Marker -Raw).Trim() -ne 'generated') {
    throw "Invalid campus ready marker: $Marker"
}
Write-Host "Using the campus already installed at $Target. No files were replaced."
