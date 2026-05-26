@echo off
chcp 65001 >nul
title Browser Agent Setup
color 0A
cls

echo.
echo  ============================================================
echo        BROWSER AGENT - AUTOMATIC SETUP
echo        Do NOT close this window.
echo        Duration: 3-5 minutes.
echo  ============================================================
echo.
timeout /t 2 >nul

if exist "venv\Scripts\uvicorn.exe" (
    echo  [OK] Already installed. Run START.bat to launch.
    pause
    exit /b 0
)

:: ── STEP 1: Python ──────────────────────────────────────────────
echo  [1/5]  Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!]  Python not found. Downloading...
    powershell -Command "(New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe','%TEMP%\py_setup.exe')"
    echo  [!]  Installer will open.
    echo  [!]  IMPORTANT: check  Add python.exe to PATH  then click Install Now
    start /wait %TEMP%\py_setup.exe
    del %TEMP%\py_setup.exe >nul 2>&1
    :: Force add Python to PATH using PowerShell
    powershell -Command "$p = [System.Environment]::GetEnvironmentVariable('PATH','Machine'); if ($p -notlike '*Python312*') { $py = Get-ChildItem 'C:\Users' -Recurse -Filter 'python.exe' -ErrorAction SilentlyContinue | Select-Object -First 1; if ($py) { $dir = $py.DirectoryName; [System.Environment]::SetEnvironmentVariable('PATH', $p + ';' + $dir, 'Machine') } }" >nul 2>&1
    :: Also try standard locations
    if exist "C:\Python312\python.exe" set "PATH=%PATH%;C:\Python312;C:\Python312\Scripts"
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts"
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [ERROR] Please RESTART PC and run INSTALL.bat again.
        pause & exit /b 1
    )
)
python --version
echo  [OK] Python ready

:: ── STEP 2: Node.js ─────────────────────────────────────────────
echo.
echo  [2/5]  Checking Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!]  Node.js not found. Downloading...
    powershell -Command "(New-Object Net.WebClient).DownloadFile('https://nodejs.org/dist/v20.15.0/node-v20.15.0-x64.msi','%TEMP%\node_setup.msi')"
    echo  [!]  Installing Node.js...
    start /wait msiexec /i "%TEMP%\node_setup.msi" /quiet /norestart
    del %TEMP%\node_setup.msi >nul 2>&1
    :: Force add Node to PATH right now - all possible locations
    set "NODE_PATH=C:\Program Files\nodejs"
    if exist "C:\Program Files (x86)\nodejs\node.exe" set "NODE_PATH=C:\Program Files (x86)\nodejs"
    :: Add to current session PATH
    set "PATH=%PATH%;%NODE_PATH%"
    :: Add to system PATH permanently via registry
    powershell -Command "$old = [System.Environment]::GetEnvironmentVariable('PATH','Machine'); if ($old -notlike '*nodejs*') { [System.Environment]::SetEnvironmentVariable('PATH', $old + ';%NODE_PATH%', 'Machine') }" >nul 2>&1
    :: Also add npm global to PATH
    set "NPM_PATH=%APPDATA%\npm"
    set "PATH=%PATH%;%NPM_PATH%"
    powershell -Command "$old = [System.Environment]::GetEnvironmentVariable('PATH','User'); if ($old -notlike '*npm*') { [System.Environment]::SetEnvironmentVariable('PATH', $old + ';%APPDATA%\npm', 'User') }" >nul 2>&1
)
:: Final check with full paths
node --version >nul 2>&1
if %errorlevel% neq 0 (
    if exist "C:\Program Files\nodejs\node.exe" (
        set "PATH=%PATH%;C:\Program Files\nodejs;%APPDATA%\npm"
    )
)
"C:\Program Files\nodejs\node.exe" --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PATH=%PATH%;C:\Program Files\nodejs;%APPDATA%\npm"
)
node --version
echo  [OK] Node.js ready

:: ── STEP 3: Fix PowerShell execution policy ─────────────────────
echo.
echo  [3/5]  Fixing npm permissions...
powershell -Command "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force" >nul 2>&1
echo  [OK] Done

:: ── STEP 4: Python venv + packages ─────────────────────────────
echo.
echo  [4/5]  Installing Python packages...
if not exist "venv" (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to create virtual environment.
        pause & exit /b 1
    )
)
venv\Scripts\pip.exe install --upgrade pip --quiet
venv\Scripts\pip.exe install -r requirements.txt
if %errorlevel% neq 0 (
    echo  [ERROR] Failed to install Python packages.
    pause & exit /b 1
)
echo  [OK] Python packages installed

:: ── STEP 5: Puppeteer ───────────────────────────────────────────
echo.
echo  [5/5]  Installing browser automation tools...
:: Use full path to npm to avoid PATH issues
if exist "C:\Program Files\nodejs\npm.cmd" (
    "C:\Program Files\nodejs\npm.cmd" install -g @modelcontextprotocol/server-puppeteer
) else (
    cmd /c npm install -g @modelcontextprotocol/server-puppeteer
)
echo  [OK] Puppeteer installed

echo.
echo  ============================================================
echo        SETUP COMPLETE!
echo.
echo        Next steps:
echo        1. Open the .env file with Notepad
echo        2. Replace  sk-ant-YOUR_KEY_HERE  with your real key
echo           Get key at: https://console.anthropic.com
echo        3. Double-click START.bat to launch
echo  ============================================================
echo.
pause
