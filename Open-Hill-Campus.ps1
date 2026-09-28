param([switch]$Verify)

$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    $campusConfig = Get-Content -LiteralPath 'server-assets/hill-campus-current.json' -Raw | ConvertFrom-Json
    foreach ($requiredPath in @($campusConfig.world, $campusConfig.start_view)) {
        if (-not (Test-Path -LiteralPath $requiredPath)) {
            throw "The selected campus file is missing: $requiredPath"
        }
    }

    # Find the existing runtime even when a fresh terminal has an older PATH.
    $uvExecutable = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
    if (-not (Test-Path -LiteralPath $uvExecutable)) {
        $uvCommand = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $uvCommand) {
            throw 'The prepared Python launcher could not be found on this computer.'
        }
        $uvExecutable = $uvCommand.Source
    }

    Write-Host 'Opening the Hill campus in Creative mode at the Quad...'
    Write-Host 'Your campus player save is preserved between visits.'
    $launchArguments = @(
        'run', '--python', '3.13', 'python', 'scripts/run_chapel_native_qa.py',
        '--interactive', '--world', $campusConfig.world,
        '--playable-dir', $campusConfig.playable_dir,
        '--start-view-config', $campusConfig.start_view,
        '--render-distance', [string]$campusConfig.render_distance,
        '--timeout-seconds', '600'
    )
    if ($Verify) {
        $launchArguments += '--exit-when-ready'
    }
    & $uvExecutable @launchArguments
    exit $LASTEXITCODE
}
catch {
    Write-Host ("Campus launch failed: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
