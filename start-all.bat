@echo off
setlocal enabledelayedexpansion

rem ============================================================
rem  TalentFlow start-all.bat
rem  Start MySQL service + Backend FastAPI (8080) + Frontend Vite (3001)
rem  Usage: double click, or run in cmd: start-all.bat
rem ============================================================

set "ROOT=%~dp0"
set "FRONTEND=%ROOT%talent-flow-web"
set "BACKEND=%ROOT%talent-flow-backend"
set "PYEXE=%BACKEND%\.venv\Scripts\python.exe"
rem MySQL Windows service name; check with: sc query MySQL
set "MYSQL_SERVICE=MySQL"

echo ============================================
echo  TalentFlow - start MySQL + backend + frontend
echo ============================================

rem ---------- 1. MySQL ----------
sc query "%MYSQL_SERVICE%" >nul 2>&1
if errorlevel 1 (
  echo [MySQL] Service "%MYSQL_SERVICE%" not found. Set MYSQL_SERVICE at the top of this script.
) else (
  for /f "tokens=4" %%s in ('sc query "%MYSQL_SERVICE%" ^| findstr /i "STATE"') do set "DB_STATE=%%s"
  if /i "!DB_STATE!"=="RUNNING" (
    echo [MySQL] Already running.
  ) else (
    echo [MySQL] Starting service "%MYSQL_SERVICE%" ...
    net start "%MYSQL_SERVICE%" >nul 2>&1
    if errorlevel 1 (
      echo [MySQL] Start failed: administrator privileges required. Re-run as Administrator.
    ) else (
      echo [MySQL] Started.
    )
  )
)

rem ---------- 2. Backend ----------
if not exist "%PYEXE%" (
  echo [Backend] venv not found: %PYEXE%
  echo           Run first: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
start "TalentFlow-Backend" /D "%BACKEND%" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload"
echo [Backend] Started: http://localhost:8080/docs

rem ---------- 3. Frontend ----------
if not exist "%FRONTEND%\node_modules" (
  echo [Frontend] node_modules missing, running npm install ...
  pushd "%FRONTEND%" && call npm install && popd
)
start "TalentFlow-Frontend" /D "%FRONTEND%" cmd /k "npm run dev"
echo [Frontend] Started: http://localhost:3001

echo.
echo All services started. Stop with stop-all.bat
goto :eof
