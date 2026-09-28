param(
    [Parameter(Mandatory = $true)]
    [string]$WorldPath,
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot,
    [string]$ConfigTemplate = "runtime/campus-reconstruction/voxelearth-server-smoke/bluemap-config",
    [string]$BlueMapJar = "runtime/tools/bluemap/bluemap-5.23-cli.jar",
    [string]$MinecraftVersion = "1.20.4",
    [string]$MapName = "Hill School Main Buildings QA",
    [int]$MinX = -32,
    [int]$MaxX = 32,
    [int]$MinZ = -32,
    [int]$MaxZ = 40,
    [int]$MinY = 70,
    [int]$MaxY = 140,
    [int]$Port = 18128,
    [switch]$Serve
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-ExistingPath([string]$PathValue) {
    return (Resolve-Path -LiteralPath $PathValue).Path
}

function Resolve-OutputPath([string]$PathValue) {
    if ([IO.Path]::IsPathRooted($PathValue)) {
        return [IO.Path]::GetFullPath($PathValue)
    }
    return [IO.Path]::GetFullPath((Join-Path (Get-Location) $PathValue))
}

function Convert-ToBlueMapPath([string]$PathValue) {
    return $PathValue.Replace("\", "/")
}

function Set-ConfigValue([string]$PathValue, [string]$Key, [string]$Value) {
    $text = Get-Content -LiteralPath $PathValue -Raw
    $pattern = "(?m)^\s*#?" + [regex]::Escape($Key) + ":\s*.*$"
    $replacement = $Key + ': "' + (Convert-ToBlueMapPath $Value) + '"'
    if ($text -notmatch $pattern) {
        throw "Config key '$Key' not found in $PathValue"
    }
    $text = [regex]::Replace($text, $pattern, $replacement, 1)
    Set-Content -LiteralPath $PathValue -Value $text -Encoding UTF8
}

function Set-ConfigScalar([string]$PathValue, [string]$Key, [string]$Value) {
    $text = Get-Content -LiteralPath $PathValue -Raw
    $pattern = "(?m)^\s*#?" + [regex]::Escape($Key) + ":\s*.*$"
    $replacement = $Key + ": " + $Value
    if ($text -notmatch $pattern) {
        throw "Config key '$Key' not found in $PathValue"
    }
    $text = [regex]::Replace($text, $pattern, $replacement, 1)
    Set-Content -LiteralPath $PathValue -Value $text -Encoding UTF8
}

$resolvedWorld = Resolve-ExistingPath $WorldPath
$resolvedTemplate = Resolve-ExistingPath $ConfigTemplate
$resolvedJar = Resolve-ExistingPath $BlueMapJar
$resolvedOutput = Resolve-OutputPath $OutputRoot
$configDir = Join-Path $resolvedOutput "config"
$dataDir = Join-Path $resolvedOutput "data"
$webDir = Join-Path $resolvedOutput "web"
$renderLog = Join-Path $resolvedOutput "render.log"

New-Item -ItemType Directory -Force -Path $configDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $configDir "maps") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $configDir "storages") | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
New-Item -ItemType Directory -Force -Path $webDir | Out-Null

Copy-Item -LiteralPath (Join-Path $resolvedTemplate "core.conf") -Destination (Join-Path $configDir "core.conf") -Force
Copy-Item -LiteralPath (Join-Path $resolvedTemplate "webapp.conf") -Destination (Join-Path $configDir "webapp.conf") -Force
Copy-Item -LiteralPath (Join-Path $resolvedTemplate "webserver.conf") -Destination (Join-Path $configDir "webserver.conf") -Force
Copy-Item -LiteralPath (Join-Path $resolvedTemplate "maps/overworld.conf") -Destination (Join-Path $configDir "maps/overworld.conf") -Force
Copy-Item -LiteralPath (Join-Path $resolvedTemplate "storages/file.conf") -Destination (Join-Path $configDir "storages/file.conf") -Force

$mapConfig = Join-Path $configDir "maps/overworld.conf"
Set-ConfigValue $mapConfig "world" $resolvedWorld
Set-ConfigScalar $mapConfig "name" ('"' + $MapName + '"')
Set-ConfigScalar $mapConfig "start-pos" "{ x: 0, z: 4 }"
Set-ConfigScalar $mapConfig "min-x" $MinX
Set-ConfigScalar $mapConfig "max-x" $MaxX
Set-ConfigScalar $mapConfig "min-z" $MinZ
Set-ConfigScalar $mapConfig "max-z" $MaxZ
Set-ConfigScalar $mapConfig "min-y" $MinY
Set-ConfigScalar $mapConfig "max-y" $MaxY

Set-ConfigValue (Join-Path $configDir "core.conf") "data" $dataDir
Set-ConfigValue (Join-Path $configDir "core.conf") "file" (Join-Path $dataDir "logs/debug.log")
Set-ConfigValue (Join-Path $configDir "webapp.conf") "webroot" $webDir
Set-ConfigValue (Join-Path $configDir "webserver.conf") "webroot" $webDir
Set-ConfigScalar (Join-Path $configDir "webserver.conf") "port" $Port
Set-ConfigValue (Join-Path $configDir "storages/file.conf") "root" (Join-Path $webDir "maps")

& java -Xmx4G -jar $resolvedJar -c $configDir -v $MinecraftVersion -g -s -r -m overworld -f -l $renderLog
if ($LASTEXITCODE -ne 0) {
    throw "BlueMap render failed with exit code $LASTEXITCODE; see $renderLog"
}

$serverProcess = $null
if ($Serve) {
    $serverProcess = Start-Process -FilePath "java" -ArgumentList @(
        "-Xmx2G",
        "-jar",
        $resolvedJar,
        "-c",
        $configDir,
        "-w",
        "-l",
        (Join-Path $resolvedOutput "web.log")
    ) -WorkingDirectory $resolvedOutput -PassThru -WindowStyle Hidden
}

[pscustomobject]@{
    world = $resolvedWorld
    output = $resolvedOutput
    config = $configDir
    web = $webDir
    render_log = $renderLog
    port = $Port
    server_pid = if ($null -eq $serverProcess) { $null } else { $serverProcess.Id }
} | ConvertTo-Json
