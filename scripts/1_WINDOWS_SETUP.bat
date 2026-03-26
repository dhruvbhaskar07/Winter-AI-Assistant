@echo off
setlocal ENABLEDELAYEDEXPANSION
title Winter AI - Windows Easy Menu

cd /d %~dp0\..

set "PY_EXE=.venv\Scripts\python.exe"

:menu
cls
echo ==========================================
echo   Winter AI Windows - Easy 9 Options
echo ==========================================
echo 1. First Time Full Setup
echo 2. Create/Repair Virtual Environment
echo 3. Upgrade pip
echo 4. Install/Update Requirements
echo 5. Create .env from .env.example
echo 6. Run Desktop UI
echo 7. Run Voice/CLI Mode
echo 8. Quick Health Check
echo 9. Exit
echo ==========================================
set /p choice=Choose option (1-9): 

if "%choice%"=="1" goto first_time
if "%choice%"=="2" goto make_venv
if "%choice%"=="3" goto pip_upgrade
if "%choice%"=="4" goto install_req
if "%choice%"=="5" goto make_env
if "%choice%"=="6" goto run_ui
if "%choice%"=="7" goto run_cli
if "%choice%"=="8" goto health
if "%choice%"=="9" goto end

echo [WARN] Invalid option. Please select 1-9.
pause
goto menu

:ensure_venv
if exist "%PY_EXE%" goto :eof
echo [INFO] Creating .venv virtual environment...
py -3.10 -m venv .venv >nul 2>nul
if errorlevel 1 (
  python -m venv .venv >nul 2>nul
)
if not exist "%PY_EXE%" (
  echo [ERR] Python not found or venv creation failed.
  exit /b 1
)
echo [OK] .venv ready.
goto :eof

:first_time
echo [INFO] Running first-time full setup...
call :ensure_venv
if errorlevel 1 (
  pause
  goto menu
)
call :pip_upgrade_core
if errorlevel 1 (
  pause
  goto menu
)
call :install_req_core
if errorlevel 1 (
  pause
  goto menu
)
call :make_env_core
echo [OK] First-time setup completed.
pause
goto menu

:make_venv
call :ensure_venv
if errorlevel 1 (
  pause
  goto menu
)
pause
goto menu

:pip_upgrade
call :ensure_venv
if errorlevel 1 (
  pause
  goto menu
)
call :pip_upgrade_core
pause
goto menu

:install_req
call :ensure_venv
if errorlevel 1 (
  pause
  goto menu
)
call :install_req_core
pause
goto menu

:make_env
call :make_env_core
pause
goto menu

:run_ui
call :ensure_venv
if errorlevel 1 (
  pause
  goto menu
)
if not exist ".env" (
  echo [ERR] .env missing. Use option 5 first.
  pause
  goto menu
)
echo [INFO] Starting UI...
"%PY_EXE%" ui.py
pause
goto menu

:run_cli
call :ensure_venv
if errorlevel 1 (
  pause
  goto menu
)
if not exist ".env" (
  echo [ERR] .env missing. Use option 5 first.
  pause
  goto menu
)
echo [INFO] Starting CLI/Voice mode...
"%PY_EXE%" main.py
pause
goto menu

:health
call :ensure_venv
if errorlevel 1 (
  pause
  goto menu
)
echo [INFO] Running quick health check...
"%PY_EXE%" -c "import main, ui; print('OK: import check passed')"
if errorlevel 1 (
  echo [ERR] Health check failed.
) else (
  echo [OK] Health check passed.
)
pause
goto menu

:pip_upgrade_core
echo [INFO] Upgrading pip...
"%PY_EXE%" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERR] pip upgrade failed.
  exit /b 1
)
echo [OK] pip updated.
exit /b 0

:install_req_core
echo [INFO] Installing requirements...
"%PY_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERR] Requirements install failed.
  exit /b 1
)
echo [OK] Requirements installed.
exit /b 0

:make_env_core
if exist ".env" (
  echo [OK] .env already exists.
  exit /b 0
)
if not exist ".env.example" (
  echo [ERR] .env.example not found.
  exit /b 1
)
copy /Y ".env.example" ".env" >nul
echo [WARN] .env created. Please set API_KEY before run.
exit /b 0

:end
echo [INFO] Exiting setup menu.
exit /b 0
