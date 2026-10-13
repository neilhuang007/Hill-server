# Copies a Minecraft Java world save (a folder, or a ZIP holding one save) into a
# designated map folder such as <server>\world-templates\hill_hub, leaving player
# data behind. Add a hill-world.yml there for the arrival point and guide positions.
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Source,
    [Parameter(Mandatory)]
    [string]$Destination,
    # Also leave out mobs, item frames, paintings and other entities.
    [switch]$ExcludeEntities
)
$ErrorActionPreference = 'Stop'

$ExcludedDirectoryNames = @('players', 'playerdata', 'stats', 'advancements')
if ($ExcludeEntities) { $ExcludedDirectoryNames += 'entities' }
$ExcludedFileNames = @('session.lock', 'uid.dat')

$Destination = [IO.Path]::GetFullPath($Destination)
if ((Test-Path -LiteralPath $Destination) -and @(Get-ChildItem -LiteralPath $Destination -Force).Count) {
    throw "Refusing to merge into the existing map at $Destination. Move it aside first."
}
if (-not (Test-Path -LiteralPath $Source)) { throw "Source not found: $Source" }

$Extracted = $null
try {
    $Save = (Resolve-Path -LiteralPath $Source).Path
    if (Test-Path -LiteralPath $Save -PathType Leaf) {
        $Extracted = Join-Path ([IO.Path]::GetTempPath()) ('hill175-map-' + [Guid]::NewGuid().ToString('N'))
        Expand-Archive -LiteralPath $Save -DestinationPath $Extracted
        $Save = $Extracted
        # Minecraft exports wrap the save in one folder.
        $Inner = @(Get-ChildItem -LiteralPath $Save -Force)
        if (-not (Test-Path -LiteralPath (Join-Path $Save 'level.dat')) -and $Inner.Count -eq 1 -and $Inner[0].PSIsContainer) {
            $Save = $Inner[0].FullName
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Save 'level.dat') -PathType Leaf)) {
        throw "Not a Minecraft Java world save (no level.dat): $Source"
    }

    $Copied = 0
    foreach ($File in Get-ChildItem -LiteralPath $Save -Recurse -Force -File) {
        if ($File.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Links are not allowed: $($File.FullName)" }
        $Relative = $File.FullName.Substring($Save.TrimEnd('\', '/').Length + 1)
        $Folders = @($Relative -split '[\\/]' | Select-Object -SkipLast 1)
        if ($File.Name -in $ExcludedFileNames -or @($Folders | Where-Object { $_ -in $ExcludedDirectoryNames }).Count) {
            continue
        }
        $Target = Join-Path $Destination $Relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
        Copy-Item -LiteralPath $File.FullName -Destination $Target
        $Copied++
    }
} finally {
    if ($Extracted) { Remove-Item -LiteralPath $Extracted -Recurse -Force -ErrorAction SilentlyContinue }
}

Write-Host "Staged $Copied files at $Destination"
if (-not (Test-Path -LiteralPath (Join-Path $Destination 'hill-world.yml'))) {
    Write-Host 'No hill-world.yml: players arrive at the save''s own spawn. Add one to set the arrival point and guide positions.'
}
