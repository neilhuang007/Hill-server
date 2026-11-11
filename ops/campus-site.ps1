[CmdletBinding()]
param([ValidateSet('Start','Stop','Status')][string]$Action = 'Start', [int]$Port = 8788)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$site = Join-Path $root 'runtime/campus-site'
$state = Join-Path $site 'preview-process.json'
$java = Join-Path $env:LOCALAPPDATA 'Hill175/jdk25/bin/java.exe'
if (Test-Path -LiteralPath $state) {
    $saved = Get-Content -LiteralPath $state -Raw | ConvertFrom-Json
    $running = Get-Process -Id $saved.pid -ErrorAction SilentlyContinue
    $identity = Get-CimInstance Win32_Process -Filter "ProcessId = $($saved.pid)" -ErrorAction SilentlyContinue
    if ($running -and ($identity.CommandLine -notlike "*$root\ops\CampusSitePreview.java*")) { $running = $null }
    if ($Action -eq 'Stop') {
        if ($running) { Stop-Process -Id $running.Id }
        Remove-Item -LiteralPath $state
        Write-Output 'Local campus website stopped.'
        return
    }
    if ($running) { Write-Output "Local campus website: http://127.0.0.1:$($saved.port)"; return }
    Remove-Item -LiteralPath $state
}
if ($Action -ne 'Start') { Write-Output 'Local campus website is stopped.'; return }
try {
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    $probe.Start()
} catch { throw "Port $Port is already in use. Choose another port with -Port." }
finally { if ($probe) { $probe.Stop() } }
if (-not (Test-Path -LiteralPath (Join-Path $site 'campus.json'))) {
    throw 'Prepare the site with ops/prepare-campus-site.py first.'
}
$env:JAVA_HOME = Split-Path -Parent (Split-Path -Parent $java)
Push-Location $root
try {
    & ./gradlew.bat classes
    if ($LASTEXITCODE -ne 0) { throw 'Site compilation failed.' }
    $classPath = (Join-Path $root 'build/classes/java/main') + ';' + (Join-Path $root 'build/resources/main')
    $launcher = Join-Path $root 'ops/CampusSitePreview.java'
    $process = Start-Process -FilePath $java -WindowStyle Hidden -WorkingDirectory $root `
        -ArgumentList @('-cp', ('"' + $classPath + '"'), ('"' + $launcher + '"'), ('"' + $root + '"'), $Port) `
        -RedirectStandardOutput (Join-Path $site 'preview.log') -RedirectStandardError (Join-Path $site 'preview-errors.log') -PassThru
    $started = $process.StartTime.ToUniversalTime().ToString('o')
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 250
        if ($process.HasExited) { throw "Preview did not start. Read $site/preview-errors.log" }
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                Start-Sleep -Milliseconds 500
                if ($process.HasExited) { throw 'The website process exited while starting.' }
                break
            }
        } catch { if ($attempt -eq 39) { Stop-Process -Id $process.Id; throw 'Website did not become ready.' } }
    }
    @{pid=$process.Id; port=$Port; started=$started} | ConvertTo-Json | Set-Content -LiteralPath $state
    Write-Output "Local campus website: http://127.0.0.1:$Port"
} finally { Pop-Location }
