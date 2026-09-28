@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Open-Hill-Campus-1.21.11.ps1" %*
exit /b %errorlevel%
