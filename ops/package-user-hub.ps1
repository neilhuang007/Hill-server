param(
    [string]$Source = 'C:\Users\neil_\AppData\Roaming\ModrinthApp\profiles\Fabric 26.2\saves\New World',
    [string]$Destination = ''
)

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Assets = Join-Path $Root 'runtime\assets'
$ArchiveName = 'Hill175-Exhibition-Hub-2026-08-26.zip'
$ArchiveRoot = 'Hill175 Exhibition Hub 2026-08-26'
$ExcludedDirectoryNames = @('players', 'playerdata', 'stats', 'advancements', 'entities')
$ExcludedFileNames = @('session.lock', 'uid.dat')

if (-not (Test-Path -LiteralPath (Join-Path $Source 'level.dat') -PathType Leaf)) {
    throw "The source is not a Minecraft Java world: $Source"
}

New-Item -ItemType Directory -Force -Path $Assets | Out-Null
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $Assets $ArchiveName
}

$assetsFullPath = [System.IO.Path]::GetFullPath($Assets)
$destinationFullPath = [System.IO.Path]::GetFullPath($Destination)
if (-not $destinationFullPath.StartsWith($assetsFullPath + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "The packaged hub must be written inside $assetsFullPath"
}
if (Test-Path -LiteralPath $destinationFullPath) {
    throw "Refusing to overwrite the existing archive: $destinationFullPath"
}

$temporaryArchive = "$destinationFullPath.tmp"
if (Test-Path -LiteralPath $temporaryArchive) {
    throw "Refusing to overwrite the existing temporary archive: $temporaryArchive"
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$sourceFullPath = (Resolve-Path -LiteralPath $Source).Path
$archiveStream = [System.IO.File]::Open($temporaryArchive, [System.IO.FileMode]::CreateNew)
try {
    $archive = [System.IO.Compression.ZipArchive]::new(
        $archiveStream,
        [System.IO.Compression.ZipArchiveMode]::Create,
        $false
    )
    try {
        $files = Get-ChildItem -LiteralPath $sourceFullPath -Recurse -Force -File | Sort-Object FullName
        foreach ($file in $files) {
            $relative = [System.IO.Path]::GetRelativePath($sourceFullPath, $file.FullName)
            $segments = $relative -split '[\\/]'
            $isInExcludedDirectory = @($segments | Where-Object { $_ -in $ExcludedDirectoryNames }).Count -gt 0
            if ($file.Name -in $ExcludedFileNames -or $isInExcludedDirectory) {
                continue
            }

            $entryName = "$ArchiveRoot/$($relative.Replace('\', '/'))"
            $entry = $archive.CreateEntry($entryName, [System.IO.Compression.CompressionLevel]::Optimal)
            $entry.LastWriteTime = $file.LastWriteTimeUtc
            $input = $file.OpenRead()
            $output = $entry.Open()
            try {
                $input.CopyTo($output)
            } finally {
                $output.Dispose()
                $input.Dispose()
            }
        }
    } finally {
        $archive.Dispose()
    }
} finally {
    $archiveStream.Dispose()
}

Move-Item -LiteralPath $temporaryArchive -Destination $destinationFullPath
$hash = (Get-FileHash -LiteralPath $destinationFullPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Packaged sanitized hub: $destinationFullPath"
Write-Host "SHA-256: $hash"
