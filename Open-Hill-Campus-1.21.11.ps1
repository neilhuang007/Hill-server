param(
    [ValidatePattern('^[A-Za-z0-9_]{1,16}$')]
    [string]$PlayerName = 'HillBuilder'
)

$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    $uvExecutable = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
    if (-not (Test-Path -LiteralPath $uvExecutable)) {
        $uvCommand = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $uvCommand) {
            throw 'The prepared Python launcher could not be found on this computer.'
        }
        $uvExecutable = $uvCommand.Source
    }

    $world = 'runtime/campus-reconstruction/campus-port-1.21.11-v19b/world/level.dat'
    if (-not (Test-Path -LiteralPath $world)) {
        throw 'The prepared Minecraft 1.21.11 campus world is missing.'
    }

    Write-Host 'Opening The Hill School in Minecraft Java 1.21.11...'
    & $uvExecutable run --python 3.13 python scripts/launch_hill_campus_12111.py --player-name $PlayerName
    exit $LASTEXITCODE
}
catch {
    Write-Host ("Campus launch failed: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
