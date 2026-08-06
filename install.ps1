# Jarvis OS Installer for Windows (PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1

param(
    [switch]$SkipPipUpgrade = $false,
    [switch]$SkipConfigWizard = $false,
    [string]$InstallDir = $null
)

$ErrorActionPreference = "Stop"

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                                            ║" -ForegroundColor Cyan
Write-Host "║           Welcome to Jarvis OS Installation                ║" -ForegroundColor Cyan
Write-Host "║              Enterprise AI Agent Platform                  ║" -ForegroundColor Cyan
Write-Host "║                                                            ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "[*] Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python not found"
    }
    Write-Host "[+] Found $pythonVersion" -ForegroundColor Green
}
catch {
    Write-Host "[!] ERROR: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "[*] Please install Python 3.8+ from https://www.python.org/" -ForegroundColor Yellow
    Write-Host "[*] Make sure to check 'Add Python to PATH' during installation" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check pip
Write-Host "[*] Checking pip..." -ForegroundColor Yellow
try {
    pip --version | Out-Null
    Write-Host "[+] pip is available" -ForegroundColor Green
}
catch {
    Write-Host "[!] ERROR: pip is not available" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Upgrade pip
if (-not $SkipPipUpgrade) {
    Write-Host "[*] Upgrading pip..." -ForegroundColor Yellow
    python -m pip install --upgrade pip | Out-Null
    Write-Host "[+] pip upgraded" -ForegroundColor Green
}

# Install dependencies
Write-Host ""
Write-Host "[*] Installing dependencies..." -ForegroundColor Yellow
Write-Host "[*] This may take a few minutes..." -ForegroundColor Yellow
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] ERROR: Failed to install dependencies" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[+] Dependencies installed" -ForegroundColor Green

# Install Jarvis
Write-Host "[*] Installing Jarvis OS..." -ForegroundColor Yellow
pip install -e .
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] ERROR: Failed to install Jarvis OS" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[+] Jarvis OS installed" -ForegroundColor Green

# Create directories
Write-Host "[*] Creating directories..." -ForegroundColor Yellow
$jarvisDir = Join-Path $env:USERPROFILE ".jarvis"
@("", "config", "logs", "data") | ForEach-Object {
    $dir = Join-Path $jarvisDir $_
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}
Write-Host "[+] Created .jarvis directory at $jarvisDir" -ForegroundColor Green

# Setup configuration
Write-Host "[*] Setting up configuration..." -ForegroundColor Yellow
$configFile = Join-Path $jarvisDir "config" "settings.json"
if (-not (Test-Path $configFile)) {
    if (Test-Path "config\settings.json.template") {
        Copy-Item "config\settings.json.template" $configFile
        Write-Host "[+] Created configuration file" -ForegroundColor Green
    }
}

# Create .env file
Write-Host "[*] Creating environment file..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    $envContent = @"
# Jarvis OS Configuration
# Add your API keys here

GOOGLE_API_KEY=your_api_key_here
OLLAMA_URL=http://localhost:11434

JARVIS_DATA_DIR=$jarvisDir
JARVIS_LOG_LEVEL=INFO
"@
    Set-Content -Path ".env" -Value $envContent
    Write-Host "[+] Created .env file" -ForegroundColor Green
}

# Create desktop shortcut
Write-Host "[*] Creating desktop shortcuts..." -ForegroundColor Yellow
$desktopPath = Join-Path $env:USERPROFILE "Desktop"
$batPath = Join-Path $desktopPath "Jarvis.bat"

$batContent = @"
@echo off
cd /d "$((Get-Location).Path)"
python -m jarvis.cli
"@

Set-Content -Path $batPath -Value $batContent
Write-Host "[+] Created desktop shortcut at $batPath" -ForegroundColor Green

# Test installation
Write-Host ""
Write-Host "[*] Verifying installation..." -ForegroundColor Yellow
try {
    python -c "import jarvis; print('OK')" 2>$null | Out-Null
    Write-Host "[+] Jarvis OS verified successfully!" -ForegroundColor Green
}
catch {
    Write-Host "[!] Warning: Could not import Jarvis module" -ForegroundColor Yellow
    Write-Host "[*] This may be a PATH issue - try restarting your terminal" -ForegroundColor Yellow
}

# Installation complete
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                                                            ║" -ForegroundColor Green
Write-Host "║              Installation Complete! 🎉                     ║" -ForegroundColor Green
Write-Host "║                                                            ║" -ForegroundColor Green
Write-Host "║  Next steps:                                               ║" -ForegroundColor Green
Write-Host "║  1. Edit .env file with your API keys                      ║" -ForegroundColor Green
Write-Host "║  2. Run: jarvis                                            ║" -ForegroundColor Green
Write-Host "║  3. Or double-click 'Jarvis.bat' on your desktop           ║" -ForegroundColor Green
Write-Host "║                                                            ║" -ForegroundColor Green
Write-Host "║  Documentation:                                            ║" -ForegroundColor Green
Write-Host "║  - ENTERPRISE_INTEGRATION_GUIDE.md                         ║" -ForegroundColor Green
Write-Host "║  - PHASE_1_COMPLETION_SUMMARY.md                           ║" -ForegroundColor Green
Write-Host "║  - README.md                                               ║" -ForegroundColor Green
Write-Host "║                                                            ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

# Configuration wizard
if (-not $SkipConfigWizard) {
    $response = Read-Host "Do you want to run the configuration wizard? (Y/n)"
    if ($response -eq "" -or $response -eq "y" -or $response -eq "Y") {
        Write-Host ""
        Write-Host "[*] Starting configuration wizard..." -ForegroundColor Yellow
        python -m jarvis.setup.config_wizard
    }
}

Read-Host "Press Enter to exit"
