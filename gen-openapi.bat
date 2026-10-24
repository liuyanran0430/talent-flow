@echo off
setlocal enabledelayedexpansion

rem ============================================================
rem  Regenerate openapi.yaml/json from current FastAPI routes.
rem  Calls talent-flow-backend\scripts\export_openapi.py via app.openapi().
rem  Usage: gen-openapi.bat [output]
rem    default output = openapi.yaml (in backend root)
rem    extension .json => JSON, otherwise YAML
rem ============================================================

set "ROOT=E:\program"
set "BACKEND=%ROOT%\talent-flow-backend"
set "PYEXE=%BACKEND%\.venv\Scripts\python.exe"
set "SCRIPT=%BACKEND%\scripts\export_openapi.py"

set "OUT=%~1"
if "%OUT%"=="" set "OUT=openapi.yaml"

if not exist "%PYEXE%" (
  echo [ERROR] venv not found: %PYEXE%
  exit /b 1
)
if not exist "%SCRIPT%" (
  echo [ERROR] export script not found: %SCRIPT%
  exit /b 1
)

pushd "%BACKEND%"
echo [GEN] %OUT%
"%PYEXE%" "%SCRIPT%" -o "%OUT%"
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" (
  echo [FAIL] openapi generation failed ^(exit %RC%^)
  exit /b 1
)
echo [DONE] %BACKEND%\%OUT%
