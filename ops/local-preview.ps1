[CmdletBinding()]
param([ValidateSet('Start','Stop','Status')][string]$Action = 'Start')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot 'local-preview.py'
$runtime = Join-Path $env:LOCALAPPDATA 'Hill175/runtime/area-bedrock-v54-20261029'
if ($Action -eq 'Start') {
    if (-not (Test-Path -LiteralPath (Join-Path $runtime '.hill175-smoke-fixture'))) {
        throw 'Prepare the local campus fixture with ops/run-bedrock-smoke.py first.'
    }
    if (Test-Path -LiteralPath (Join-Path $runtime 'local-preview.json')) {
        & uv run --python 3.13 python $script status
        return
    }
    $log = Join-Path $runtime 'preview-supervisor.log'
    $errors = Join-Path $runtime 'preview-supervisor-errors.log'
    $process = Start-Process -FilePath (Get-Command uv).Source -WindowStyle Hidden -WorkingDirectory $root `
        -ArgumentList @('run','--python','3.13','python',('"' + $script + '"'),'start') `
        -RedirectStandardOutput $log -RedirectStandardError $errors -PassThru
    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        if (Test-Path -LiteralPath (Join-Path $runtime 'local-preview.json')) { break }
        if ($process.HasExited) { throw "Local server could not start. Inspect $errors" }
        Start-Sleep -Milliseconds 200
    }
    Write-Output "Local server is starting. Run .\ops\local-preview.ps1 -Action Status for its addresses."
} else {
    & uv run --python 3.13 python $script $Action.ToLowerInvariant()
    if ($LASTEXITCODE -ne 0) { throw 'Local preview command failed.' }
}
