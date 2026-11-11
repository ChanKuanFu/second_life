@echo off
setlocal
cd /d "%~dp0"
rem Use a regular Windows Python installation. The Codex-managed Python runtime
rem can start Flask but its localhost port may not be reachable from Edge.
set "SYSTEM_PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
set "PYTHON=%~dp0.venv-local\Scripts\python.exe"

if not exist "%SYSTEM_PYTHON%" (
  echo Could not find regular Windows Python at:
  echo %SYSTEM_PYTHON%
  echo Install Python 3.12 from python.org, then run this file again.
  pause
  exit /b 1
)

if not exist "%PYTHON%" (
  echo Creating a local Windows Python environment...
  "%SYSTEM_PYTHON%" -m venv "%~dp0.venv-local"
  if errorlevel 1 (
    echo Could not create the local Python environment.
    pause
    exit /b 1
  )
)

"%PYTHON%" -c "import flask, flask_cors" >nul 2>&1
if errorlevel 1 (
  echo Installing SecondLife Python dependencies...
  "%PYTHON%" -m pip install Flask==3.1.2 Flask-Cors==6.0.1
  if errorlevel 1 (
    echo Dependency installation failed. Check the internet connection and try again.
    pause
    exit /b 1
  )
)

powershell.exe -NoProfile -Command "try { $r=Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/health' -TimeoutSec 1; if($r.ok){exit 0}else{exit 1} } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
  echo Starting SecondLife API...
  rem Keep the console open after an import/startup error so the user can read it.
  start "SecondLife API" cmd.exe /k ""%PYTHON%" "%~dp0backend\app.py""
  for /l %%i in (1,1,20) do (
    powershell.exe -NoProfile -Command "try { $r=Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/health' -TimeoutSec 1; if($r.ok){exit 0}else{exit 1} } catch { exit 1 }" >nul 2>&1
    if not errorlevel 1 goto api_ready
    timeout /t 1 /nobreak >nul
  )
  echo.
  echo ERROR: SecondLife API did not respond at http://127.0.0.1:5000/api/health.
  echo Check the visible "SecondLife API" window for the Python error.
  pause
  exit /b 1
)

:api_ready
start "" "http://127.0.0.1:5000/"
echo SecondLife is running. Keep the "SecondLife API" window open while using the app.
timeout /t 5
