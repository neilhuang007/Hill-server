@echo off
setlocal
cd /d "%~dp0"
uv run --python 3.13 python scripts\run_chapel_native_qa.py --interactive
set "HILL_EXIT_CODE=%ERRORLEVEL%"
if not "%HILL_EXIT_CODE%"=="0" pause
exit /b %HILL_EXIT_CODE%
