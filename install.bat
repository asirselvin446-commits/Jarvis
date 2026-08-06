@echo off
REM Jarvis OS Installer for Windows
REM This script will install Jarvis OS and all dependencies

setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║                                                            ║
echo ║           Welcome to Jarvis OS Installation                ║
echo ║              Enterprise AI Agent Platform                  ║
echo ║                                                            ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM Check if Python is installed
echo [*] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] ERROR: Python is not installed or not in PATH
    echo [*] Please install Python 3.8+ from https://www.python.org/
    echo [*] Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [+] Found Python %PYTHON_VERSION%

REM Check if pip is available
echo [*] Checking pip...
pip --version >nul 2>&1
if errorlevel 1 (
    echo [!] ERROR: pip is not available
    pause
    exit /b 1
)

REM Upgrade pip
echo [*] Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo.
echo [*] Installing dependencies...
echo [*] This may take a few minutes...
pip install -r requirements.txt

if errorlevel 1 (
    echo [!] ERROR: Failed to install dependencies
    pause
    exit /b 1
)

REM Install Jarvis as editable package
echo.
echo [*] Installing Jarvis OS...
pip install -e .

if errorlevel 1 (
    echo [!] ERROR: Failed to install Jarvis OS
    pause
    exit /b 1
)

REM Create directories
echo [*] Creating directories...
if not exist "%USERPROFILE%\.jarvis" mkdir "%USERPROFILE%\.jarvis"
if not exist "%USERPROFILE%\.jarvis\config" mkdir "%USERPROFILE%\.jarvis\config"
if not exist "%USERPROFILE%\.jarvis\logs" mkdir "%USERPROFILE%\.jarvis\logs"
if not exist "%USERPROFILE%\.jarvis\data" mkdir "%USERPROFILE%\.jarvis\data"

echo [+] Created .jarvis directory at %USERPROFILE%\.jarvis

REM Copy configuration template
echo [*] Setting up configuration...
if not exist "%USERPROFILE%\.jarvis\config\settings.json" (
    copy config\settings.json.template "%USERPROFILE%\.jarvis\config\settings.json" >nul
    echo [+] Created configuration file
)

REM Create .env file if it doesn't exist
echo [*] Creating environment file...
if not exist .env (
    (
        echo # Jarvis OS Configuration
        echo # Add your API keys here
        echo.
        echo GOOGLE_API_KEY=your_api_key_here
        echo OLLAMA_URL=http://localhost:11434
        echo.
        echo JARVIS_DATA_DIR=%USERPROFILE%\.jarvis
        echo JARVIS_LOG_LEVEL=INFO
    ) > .env
    echo [+] Created .env file
)

REM Create Windows shortcuts
echo [*] Creating desktop shortcuts...

REM Get Python Scripts directory
for /f "delims=" %%i in ('python -c "import site; print(site.USER_SITE.replace('\\', '/'))" 2^>nul') do set PYTHON_SCRIPTS=%%i

if not defined PYTHON_SCRIPTS (
    for /f "delims=" %%i in ('python -c "import sys; print(sys.prefix.replace('\\', '/'))" 2^>nul') do set PYTHON_PREFIX=%%i
    set PYTHON_SCRIPTS=!PYTHON_PREFIX!/Scripts
)

REM Create batch launcher
(
    echo @echo off
    echo cd "%cd%"
    echo python -m jarvis.cli
) > "%USERPROFILE%\Desktop\Jarvis.bat"

echo [+] Created desktop shortcut

REM Test installation
echo.
echo [*] Verifying installation...
python -c "import jarvis; print('[+] Jarvis OS installed successfully!')" 2>nul

if errorlevel 1 (
    echo [!] Warning: Could not import Jarvis module
    echo [*] This may be a PATH issue - try restarting your terminal
)

REM Installation complete
echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║                                                            ║
echo ║              Installation Complete! 🎉                     ║
echo ║                                                            ║
echo ║  Next steps:                                               ║
echo ║  1. Set your API keys in .env file                         ║
echo ║  2. Run: jarvis                                            ║
echo ║  3. Or double-click "Jarvis.bat" on your desktop           ║
echo ║                                                            ║
echo ║  Documentation:                                            ║
echo ║  - ENTERPRISE_INTEGRATION_GUIDE.md                         ║
echo ║  - PHASE_1_COMPLETION_SUMMARY.md                           ║
echo ║  - README.md                                               ║
echo ║                                                            ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM Open configuration wizard (optional)
echo Do you want to run the configuration wizard? (Y/n)
set /p CHOICE=
if /i "%CHOICE%"=="" set CHOICE=y
if /i "%CHOICE%"=="y" (
    python -m jarvis.setup.config_wizard
)

pause
