@echo off
setlocal enabledelayedexpansion

rem ============================================================
rem  TalentFlow start script (Windows batch)
rem  Usage: start.bat [start^|stop^|restart^|status^|help]
rem    start   Start frontend(5173)+backend(8000), each in a window (default)
rem    stop    Stop services on ports 5173/8000
rem    restart Stop then start
rem    status  Show port usage
rem    help    Show this help
rem ============================================================

set "ROOT=E:\program"
set "FRONTEND=%ROOT%\talent-flow"
set "BACKEND=%ROOT%\talent-flow-backend"
set "PYEXE=%BACKEND%\.venv\Scripts\python.exe"

set "CMD=%~1"
if /i "%CMD%"=="" set "CMD=start"

if /i "%CMD%"=="start"   goto :start
if /i "%CMD%"=="stop"    goto :stop
if /i "%CMD%"=="restart" goto :restart
if /i "%CMD%"=="status"  goto :status
if /i "%CMD%"=="help"    goto :help
goto :help

:start
echo [START] Frontend Vite (5173) + Backend FastAPI (8000)
if not exist "%FRONTEND%\node_modules" (
  echo [Frontend] node_modules missing, running npm install ...
  pushd "%FRONTEND%" && call npm install && popd
)
if not exist "%PYEXE%" (
  echo [Backend] venv not found: %PYEXE%
  echo        Run first: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
start "TalentFlow-Frontend" cmd /k "cd /d %FRONTEND% && npm run dev"
start "TalentFlow-Backend"  cmd /k "cd /d %BACKEND% && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo Started. Frontend http://localhost:5173 / Backend http://localhost:8000/docs
echo Stop with: start.bat stop  or close the windows.
goto :eof

:stop
echo [STOP] Closing services on 5173/8000 ...
call :killport 5173
call :killport 8000
goto :eof

:restart
call :stop
timeout /t 1 /nobreak >nul
call :start
goto :eof

:status
echo [STATUS]
call :portstatus 5173
call :portstatus 8000
goto :eof

:help
echo Usage: start.bat [start^|stop^|restart^|status^|help]
echo   start   Start frontend and backend (default)
echo   stop    Stop frontend and backend
echo   restart Restart frontend and backend
echo   status  Show port usage
echo   help    Show this help
goto :eof

:killport
set "PORT=%~1"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":!PORT! " ^| findstr "LISTENING"') do (
  echo   kill PID %%a on :!PORT!
  taskkill /F /PID %%a >nul 2>&1
)
goto :eof

:portstatus
set "PORT=%~1"
set "INFO=not listening"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":!PORT! " ^| findstr "LISTENING"') do (
  set "INFO=LISTENING (PID %%a)"
)
echo   :!PORT! !INFO!
goto :eof
