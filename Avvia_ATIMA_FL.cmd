@echo off
setlocal
rem Start in the repository containing this file, from any working directory.
set "ATIMA_SCRIPT=%~dp0Start-ATIMA.ps1"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%ATIMA_SCRIPT%" %*
exit /b %ERRORLEVEL%
