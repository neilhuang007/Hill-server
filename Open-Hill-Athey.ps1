$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& uv run --python 3.13 python scripts/run_chapel_native_qa.py --interactive --world runtime/campus-reconstruction/athey-v8-2x/world --playable-dir runtime/campus-reconstruction/athey-playable-v8-2x --start-view-config runtime/campus-reconstruction/athey-v8-2x/play-start.json --render-distance 24
exit $LASTEXITCODE
