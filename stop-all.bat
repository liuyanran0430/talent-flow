@echo off
setlocal enabledelayedexpansion

rem ============================================================
rem  TalentFlow stop-all.bat
rem  Stop frontend (3001) and backend (8080). MySQL service is left running.
rem  Usage: double click, or run in cmd: stop-all.bat
rem ============================================================

echo ============================================
echo  TalentFlow - stop frontend and backend
echo ============================================

call :killport 3001
call :killport 8080

echo.
echo Done. MySQL service is left running.
goto :eof

:killport
set "PORT=%~1"
set "FOUND="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":!PORT! " ^| findstr "LISTENING"') do (
  echo   [port !PORT!] kill PID %%a
  taskkill /F /PID %%a >nul 2>&1
  set "FOUND=1"
)
if not defined FOUND echo   [port !PORT!] not running
goto :eof
