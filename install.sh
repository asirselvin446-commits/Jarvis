#!/bin/bash
# Jarvis OS Installer for Linux/macOS
# Usage: bash install.sh

set -e

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║           Welcome to Jarvis OS Installation                ║"
echo "║              Enterprise AI Agent Platform                  ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Detect OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
else
    OS="unknown"
fi

echo "[*] Detected OS: $OS"
echo ""

# Check Python
echo "[*] Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "[!] ERROR: Python 3 is not installed"
    echo "[*] Install Python 3.8+ using:"
    
    if [ "$OS" = "linux" ]; then
        echo "    Ubuntu/Debian: sudo apt-get install python3 python3-pip python3-venv"
        echo "    Fedora: sudo dnf install python3 python3-pip"
        echo "    Arch: sudo pacman -S python"
    elif [ "$OS" = "macos" ]; then
        echo "    brew install python3"
    fi
    
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "[+] Found Python $PYTHON_VERSION"

# Check pip
echo "[*] Checking pip..."
if ! command -v pip3 &> /dev/null; then
    echo "[!] ERROR: pip3 is not available"
    exit 1
fi

echo "[+] pip3 is available"
echo ""

# Upgrade pip
echo "[*] Upgrading pip..."
python3 -m pip install --upgrade pip

# Create virtual environment (optional)
echo "[*] Setting up Python environment..."
if [ ! -d "venv" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv venv
    echo "[+] Virtual environment created"
fi

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    echo "[*] Activating virtual environment..."
    source venv/bin/activate
fi

# Install dependencies
echo ""
echo "[*] Installing dependencies..."
echo "[*] This may take a few minutes..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "[!] ERROR: Failed to install dependencies"
    exit 1
fi

echo "[+] Dependencies installed"

# Install Jarvis
echo "[*] Installing Jarvis OS..."
pip install -e .

if [ $? -ne 0 ]; then
    echo "[!] ERROR: Failed to install Jarvis OS"
    exit 1
fi

echo "[+] Jarvis OS installed"

# Create directories
echo "[*] Creating directories..."
mkdir -p ~/.jarvis/config
mkdir -p ~/.jarvis/logs
mkdir -p ~/.jarvis/data
echo "[+] Created .jarvis directory at ~/.jarvis"

# Setup configuration
echo "[*] Setting up configuration..."
if [ ! -f ~/.jarvis/config/settings.json ]; then
    if [ -f config/settings.json.template ]; then
        cp config/settings.json.template ~/.jarvis/config/settings.json
        echo "[+] Created configuration file"
    fi
fi

# Create .env file
echo "[*] Creating environment file..."
if [ ! -f .env ]; then
    cat > .env << 'EOF'
# Jarvis OS Configuration
# Add your API keys here

GOOGLE_API_KEY=your_api_key_here
OLLAMA_URL=http://localhost:11434

JARVIS_DATA_DIR=~/.jarvis
JARVIS_LOG_LEVEL=INFO
EOF
    echo "[+] Created .env file"
fi

# Create launcher script
echo "[*] Creating launcher script..."
mkdir -p ~/bin
cat > ~/bin/jarvis << 'EOF'
#!/bin/bash
cd "$(dirname "$0")/.."
python3 -m jarvis.cli "$@"
EOF
chmod +x ~/bin/jarvis
echo "[+] Created launcher at ~/bin/jarvis"

# Test installation
echo ""
echo "[*] Verifying installation..."
python3 -c "import jarvis; print('[+] Jarvis OS installed successfully!')" 2>/dev/null || \
    echo "[!] Warning: Could not import Jarvis module (this may be normal)"

# Installation complete
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║              Installation Complete! 🎉                     ║"
echo "║                                                            ║"
echo "║  Next steps:                                               ║"
echo "║  1. Edit .env file with your API keys                      ║"
echo "║  2. Run: jarvis                                            ║"
echo "║  3. Or: source venv/bin/activate && jarvis                 ║"
echo "║                                                            ║"
echo "║  Documentation:                                            ║"
echo "║  - ENTERPRISE_INTEGRATION_GUIDE.md                         ║"
echo "║  - PHASE_1_COMPLETION_SUMMARY.md                           ║"
echo "║  - README.md                                               ║"
echo "║                                                            ║"
echo "║  To deactivate virtual environment:                        ║"
echo "║  deactivate                                                ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Ask to run config wizard
read -p "Do you want to run the configuration wizard? (Y/n): " -r
echo
if [[ $REPLY =~ ^[Yy]$ ]] || [ -z "$REPLY" ]; then
    echo "[*] Starting configuration wizard..."
    python3 -m jarvis.setup.config_wizard
fi

echo "[*] Installation finished!"
echo "[*] Remember to activate virtual environment with: source venv/bin/activate"
