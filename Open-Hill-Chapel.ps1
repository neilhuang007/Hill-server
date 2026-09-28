$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& uv run --python 3.13 python scripts/run_chapel_native_qa.py --interactive
exit $LASTEXITCODE
