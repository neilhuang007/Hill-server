param(
    [int]$PidToWatch = 73824,
    [string]$RunRoot = "E:\projects\Hill-server\runtime\campus-reconstruction\voxelearth-server-smoke",
    [string]$WorldName = "hill_school_voxelearth_full_20260830_2207",
    [string]$BlueMapJar = "E:\projects\Hill-server\runtime\tools\bluemap\bluemap-5.23-cli.jar",
    [string]$MinecraftVersion = "1.20.4",
    [int]$BlueMapPort = 18101,
    [int]$PollSeconds = 60
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$worldPath = Join-Path $RunRoot $WorldName
$manifestPath = Join-Path $worldPath "voxelearth-hill-manifest.json"
$watchDir = Join-Path $RunRoot "watch-logs"
$qaRoot = Join-Path $RunRoot ("bluemap-qa-full-" + $WorldName)
$configSource = Join-Path $RunRoot "bluemap-config"
$configDir = Join-Path $RunRoot ("bluemap-config-full-" + $WorldName)
$watchLog = Join-Path $watchDir ("watch-" + $WorldName + ".log")
$renderLog = Join-Path $RunRoot ("bluemap-render-full-" + $WorldName + ".log")
$webLog = Join-Path $RunRoot ("bluemap-web-full-" + $WorldName + ".log")
$rconScript = Join-Path $RunRoot "send-rcon.mjs"

function Convert-ToBlueMapPath([string]$PathValue) {
    return $PathValue.Replace("\", "/")
}

function Write-WatchLog([string]$Message) {
    New-Item -ItemType Directory -Force -Path $watchDir | Out-Null
    $line = "[{0:yyyy-MM-dd HH:mm:ss}] {1}" -f (Get-Date), $Message
    $line | Tee-Object -FilePath $watchLog -Append
}

function Get-RegionSummary {
    $regionDir = Join-Path $worldPath "region"
    if (-not (Test-Path -LiteralPath $regionDir)) {
        return "regions=0 bytes=0"
    }
    $files = @(Get-ChildItem -LiteralPath $regionDir -File -ErrorAction SilentlyContinue)
    $bytes = ($files | Measure-Object Length -Sum).Sum
    if ($null -eq $bytes) {
        $bytes = 0
    }
    return "regions=$($files.Count) bytes=$bytes"
}

function Set-ConfigValue([string]$PathValue, [string]$Key, [string]$Value) {
    $text = Get-Content -LiteralPath $PathValue -Raw
    $pattern = "(?m)^" + [regex]::Escape($Key) + ":\s*.*$"
    $replacement = $Key + ': "' + (Convert-ToBlueMapPath $Value) + '"'
    if ($text -match $pattern) {
        $text = [regex]::Replace($text, $pattern, $replacement)
    } else {
        $text = $text.TrimEnd() + [Environment]::NewLine + $replacement + [Environment]::NewLine
    }
    Set-Content -LiteralPath $PathValue -Value $text -Encoding UTF8
}

function Set-ConfigScalar([string]$PathValue, [string]$Key, [string]$Value) {
    $text = Get-Content -LiteralPath $PathValue -Raw
    $pattern = "(?m)^" + [regex]::Escape($Key) + ":\s*.*$"
    $replacement = $Key + ": " + $Value
    if ($text -match $pattern) {
        $text = [regex]::Replace($text, $pattern, $replacement)
    } else {
        $text = $text.TrimEnd() + [Environment]::NewLine + $replacement + [Environment]::NewLine
    }
    Set-Content -LiteralPath $PathValue -Value $text -Encoding UTF8
}

function Invoke-Rcon([string]$Command) {
    if (-not (Test-Path -LiteralPath $rconScript)) {
        Write-WatchLog "RCON helper missing: $rconScript"
        return
    }
    try {
        $output = & node $rconScript $Command 2>&1
        Write-WatchLog "RCON '$Command': $($output -join ' ')"
    } catch {
        Write-WatchLog "RCON '$Command' failed: $($_.Exception.Message)"
    }
}

function Prepare-BlueMapConfig {
    if (-not (Test-Path -LiteralPath $BlueMapJar)) {
        throw "BlueMap jar missing: $BlueMapJar"
    }
    if (-not (Test-Path -LiteralPath $configSource)) {
        throw "BlueMap source config missing: $configSource"
    }
    if (-not (Test-Path -LiteralPath $configDir)) {
        Copy-Item -LiteralPath $configSource -Destination $configDir -Recurse
    }
    New-Item -ItemType Directory -Force -Path $qaRoot | Out-Null

    Set-ConfigValue (Join-Path $configDir "maps\overworld.conf") "world" $worldPath
    Set-ConfigScalar (Join-Path $configDir "maps\overworld.conf") "name" '"Hill School VoxelEarth Full Campus"'
    Set-ConfigScalar (Join-Path $configDir "maps\overworld.conf") "start-pos" "{ x: 0, z: 0 }"
    Set-ConfigValue (Join-Path $configDir "core.conf") "data" (Join-Path $qaRoot "data")
    Set-ConfigValue (Join-Path $configDir "core.conf") "file" (Join-Path $qaRoot "data\logs\debug.log")
    Set-ConfigValue (Join-Path $configDir "webapp.conf") "webroot" (Join-Path $qaRoot "web")
    Set-ConfigValue (Join-Path $configDir "webserver.conf") "webroot" (Join-Path $qaRoot "web")
    Set-ConfigScalar (Join-Path $configDir "webserver.conf") "port" $BlueMapPort
    Set-ConfigValue (Join-Path $configDir "storages\file.conf") "root" (Join-Path $qaRoot "web\maps")

    return $configDir
}

Write-WatchLog "Watching VoxelEarth run pid=$PidToWatch world=$WorldName path=$worldPath"

while ($true) {
    $process = Get-Process -Id $PidToWatch -ErrorAction SilentlyContinue
    $hasManifest = Test-Path -LiteralPath $manifestPath
    if ($hasManifest) {
        Write-WatchLog "Manifest detected: $manifestPath"
        break
    }
    if ($null -eq $process) {
        Write-WatchLog "Watched process exited before manifest. $(Get-RegionSummary)"
        exit 2
    }
    $workingSetMb = [math]::Round($process.WorkingSet64 / 1MB, 1)
    $privateMb = [math]::Round($process.PrivateMemorySize64 / 1MB, 1)
    $cpu = [math]::Round($process.CPU, 1)
    Write-WatchLog "alive cpu=${cpu}s ws=${workingSetMb}MB private=${privateMb}MB $(Get-RegionSummary) manifest=false"
    Start-Sleep -Seconds $PollSeconds
}

Invoke-Rcon "save-all flush"
Start-Sleep -Seconds 5
Invoke-Rcon "stop"

$deadline = (Get-Date).AddMinutes(5)
while ((Get-Date) -lt $deadline) {
    $process = Get-Process -Id $PidToWatch -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Write-WatchLog "Paper process exited cleanly after manifest."
        break
    }
    Write-WatchLog "Waiting for Paper process to stop after manifest."
    Start-Sleep -Seconds 10
}

try {
    $config = Prepare-BlueMapConfig
    Write-WatchLog "Starting BlueMap render config=$config output=$qaRoot"
    & java -Xmx6G -jar $BlueMapJar -c $config -v $MinecraftVersion -g -s -r -m overworld -f -l $renderLog
    $renderExit = $LASTEXITCODE
    Write-WatchLog "BlueMap render exited code=$renderExit log=$renderLog"
    if ($renderExit -eq 0) {
        $webProcess = Start-Process -FilePath "java" -ArgumentList @(
            "-Xmx2G",
            "-jar",
            $BlueMapJar,
            "-c",
            $config,
            "-w",
            "-l",
            $webLog
        ) -WorkingDirectory $RunRoot -PassThru -WindowStyle Hidden
        Write-WatchLog "BlueMap webserver started pid=$($webProcess.Id) port=$BlueMapPort log=$webLog"
    }
    exit $renderExit
} catch {
    Write-WatchLog "BlueMap QA failed: $($_.Exception.Message)"
    exit 3
}
