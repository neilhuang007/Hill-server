param(
    [Parameter(Mandatory = $true)] [string] $Pack,
    [string] $Labels,
    [int] $WidgetWidth = 370,
    [switch] $KeepTrailingGap,
    [string] $DialogCapture,
    [string] $Version = '26.3',
    [string] $ClientRoot = (Join-Path $env:APPDATA '.minecraft'),
    [string] $JavaHome = (Join-Path $env:LOCALAPPDATA 'Hill175/jdk25')
)

$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$packPath = (Resolve-Path -LiteralPath $Pack).Path
if ($Version -notmatch '^\d+\.\d+(\.\d+)?$') { throw 'Supply an installed release version such as 26.3.' }
$versionFolder = Join-Path $ClientRoot ('versions/' + $Version)
$clientJar = (Resolve-Path -LiteralPath (Join-Path $versionFolder ($Version + '.jar'))).Path
$metadata = Get-Content -LiteralPath (Join-Path $versionFolder ($Version + '.json')) -Raw | ConvertFrom-Json
$libraries = @($metadata.libraries | ForEach-Object {
    if ($_.downloads.artifact.path) { Join-Path $ClientRoot ('libraries/' + $_.downloads.artifact.path) }
} | Where-Object { Test-Path -LiteralPath $_ })
$clientClasspath = [string]::Join([IO.Path]::PathSeparator, @($clientJar) + $libraries)
$classes = Join-Path $workspace ('runtime/official-map-dialog-check/' + [Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $classes -Force | Out-Null
$compiler = (Resolve-Path -LiteralPath (Join-Path $JavaHome 'bin/javac.exe')).Path
$java = (Resolve-Path -LiteralPath (Join-Path $JavaHome 'bin/java.exe')).Path
$helperName = if ($Labels) { 'OfficialMapLabelHits' } else { 'OfficialMapDialogBounds' }
$source = Join-Path $workspace ('tests/' + $helperName + '.java')

& $compiler -cp $clientClasspath -d $classes $source
if ($LASTEXITCODE -ne 0) { throw 'Could not compile the installed client map regression.' }
Write-Output ('Checking ' + $packPath + ' against unmodified Minecraft ' + $Version + ' client classes.')
$javaArguments = @('-Djava.awt.headless=true', '-cp', ($clientClasspath + [IO.Path]::PathSeparator + $classes),
    ('org.thehill.smoke.' + $helperName), $packPath)
if ($Labels) { $javaArguments += @((Resolve-Path -LiteralPath $Labels).Path, [string]$WidgetWidth, $KeepTrailingGap.IsPresent.ToString().ToLowerInvariant()) }
if ($DialogCapture) {
    if (-not $Labels) { throw 'DialogCapture requires Labels.' }
    $javaArguments += (Resolve-Path -LiteralPath $DialogCapture).Path
}
& $java @javaArguments
if ($LASTEXITCODE -ne 0) { throw 'The official map failed native client geometry checks.' }
