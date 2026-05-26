@echo off
chcp 65001 >nul
title Browser Agent
color 0A
cls

echo.
echo  ============================================================
echo        BROWSER AGENT - STARTING
echo  ============================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo  [ERROR] Not installed yet!
    echo          Please run INSTALL.bat first.
    echo.
    pause
    exit /b 1
)

if not exist ".env" (
    echo  [ERROR] Missing .env file!
    echo.
    echo          Open Notepad and create a file named .env
    echo          Put this line inside:
    echo.
    echo          ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE
    echo.
    echo          Get your key at: https://console.anthropic.com
    echo.
    pause
    exit /b 1
)

findstr /C:"sk-ant-YOUR_KEY_HERE" .env >nul 2>&1
if %errorlevel% equ 0 (
    echo  [ERROR] API key not set!
    echo.
    echo          Open .env with Notepad and replace:
    echo          sk-ant-YOUR_KEY_HERE
    echo          with your real key from https://console.anthropic.com
    echo.
    pause
    exit /b 1
)

echo  [OK] Starting server...
echo  [OK] Browser will open in 3 seconds...
echo.
echo  Address: http://localhost:8000
echo.
echo  Accounts:
echo    admin / admin123
echo    alice / alice123
echo    bob   / bob123
echo.
echo  To stop: press Ctrl+C
echo  ============================================================
echo.

start "" cmd /c "timeout /t 3 >nul && start http://localhost:8000"

venv\Scripts\uvicorn.exe server:app --host 0.0.0.0 --port 8000
pause
