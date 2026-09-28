@echo off
setlocal
cd /d "%~dp0"
uv run --python 3.13 python scripts\run_chapel_native_qa.py --interactive --world runtime/campus-reconstruction/athey-v4/world --playable-dir runtime/campus-reconstruction/athey-playable-v4 --start-view-config runtime/campus-reconstruction/athey-v4/play-start.json --render-distance 32
set "HILL_ATHEY_EXIT_CODE=%ERRORLEVEL%"
if not "%HILL_ATHEY_EXIT_CODE%"=="0" pause
exit /b %HILL_ATHEY_EXIT_CODE%
