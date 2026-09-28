@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Open-Hill-Campus.ps1" %*
exit /b %errorlevel%
