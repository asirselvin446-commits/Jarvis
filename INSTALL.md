# Jarvis OS Installation Guide

**Jarvis OS** is an enterprise-grade autonomous AI agent platform. Follow this guide to install and configure it on your system.

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Quick Installation](#quick-installation)
3. [Detailed Installation](#detailed-installation)
4. [Configuration](#configuration)
5. [Verification](#verification)
6. [Troubleshooting](#troubleshooting)
7. [Uninstallation](#uninstallation)

## System Requirements

### Minimum Requirements
- **OS**: Windows 10+, macOS 10.14+, or Linux (Ubuntu 18.04+, Fedora 30+, etc.)
- **Python**: 3.8 or higher
- **RAM**: 4 GB (8 GB recommended)
- **Disk Space**: 2 GB for installation + dependencies
- **Internet**: Required for cloud features (optional)

### Optional Requirements
- **Ollama**: For local LLM support (download from [ollama.ai](https://ollama.ai))
- **GPU**: NVIDIA GPU for ML features (CUDA 11.8+)
- **Microphone**: For voice features
- **Camera**: For vision features

## Quick Installation

### Windows (Automatic)

**Option 1: Batch Script (Simplest)**
```batch
# Run as Administrator
install.bat
```

**Option 2: PowerShell (Recommended)**
```powershell
# Right-click PowerShell → Run as Administrator
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope CurrentUser -Force
.\install.ps1
```

**Option 3: Manual (pip)**
```bash
pip install -r requirements.txt
pip install -e .
```

### macOS & Linux

```bash
# Make installer executable
chmod +x install.sh

# Run installer
./install.sh

# This will create a virtual environment and install all dependencies
```

## Detailed Installation

### Step 1: Install Python

#### Windows
1. Download Python 3.10+ from [python.org](https://www.python.org/downloads/)
2. Run the installer
3. **Important**: Check "Add Python to PATH"
4. Click "Install Now"

#### macOS
```bash
# Using Homebrew
brew install python3

# Or download from python.org
```

#### Linux
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3 python3-pip python3-venv

# Fedora
sudo dnf install python3 python3-pip

# Arch
sudo pacman -S python
```

### Step 2: Clone or Extract Repository

```bash
# Clone from GitHub
git clone https://github.com/asirselvin446-commits/Jarvis.git
cd Jarvis

# Or extract ZIP file and cd into directory
```

### Step 3: Create Virtual Environment (Recommended)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 4: Install Dependencies

```bash
# Basic installation
pip install -r requirements.txt

# Or with cloud features
pip install -r requirements.txt
pip install google-cloud-speech google-cloud-texttospeech

# Or with vision features
pip install -r requirements.txt
pip install opencv-python pillow

# Or everything
pip install -r requirements.txt[all]
```

### Step 5: Install Jarvis OS

```bash
# Development installation (editable)
pip install -e .

# Or production installation
pip install .
```

### Step 6: Verify Installation

```bash
# Check if installation succeeded
python -c "import jarvis; print('✓ Jarvis installed successfully!')"

# List available commands
jarvis --help

# Check version
jarvis --version
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Cloud LLM API Key (optional)
GOOGLE_API_KEY=your_api_key_here

# Local LLM
OLLAMA_URL=http://localhost:11434

# Data directory
JARVIS_DATA_DIR=~/.jarvis

# Logging
JARVIS_LOG_LEVEL=INFO

# Voice (optional)
MICROPHONE_DEVICE=default
SPEAKER_DEVICE=default
```

### Configuration File

Edit `~/.jarvis/config/settings.json`:

```json
{
  "name": "Jarvis",
  "version": "1.0.0",
  "voice": {
    "enabled": true,
    "language": "en-US",
    "wake_words": ["jarvis", "hey jarvis", "wake up"],
    "sensitivity": 0.5
  },
  "lllm": {
    "model_type": "auto",
    "cloud_model": "gemini-1.5-flash",
    "local_model": "qwen2.5:7b",
    "timeout": 60
  },
  "screen": {
    "monitoring_enabled": true,
    "check_interval": 5
  },
  "system": {
    "auto_optimize": true,
    "monitor_resources": true
  }
}
```

### Optional: Setup Ollama for Local LLM

```bash
# Install Ollama
# Visit: https://ollama.ai

# Download model
ollama pull qwen2.5:7b

# Start Ollama (runs as service)
ollama serve
```

### Optional: Setup Google Cloud API

1. Create a Google Cloud project
2. Enable Speech-to-Text and Text-to-Speech APIs
3. Create a service account and download JSON key
4. Add to `.env`:
   ```env
   GOOGLE_API_KEY=your_api_key_here
   ```

## Verification

### Test Basic Functionality

```bash
# 1. Test Python environment
python --version

# 2. Test Jarvis import
python -c "from jarvis.core.voice_orchestrator import get_voice_orchestrator; print('✓')"

# 3. Test all systems
python -c "
from jarvis.core.dual_model_llm import get_dual_model_provider
from jarvis.core.universal_executor import get_command_executor
from jarvis.core.system_manager import get_system_manager
print('✓ All systems loaded successfully')
"

# 4. Run CLI
jarvis --version
```

### Test Features

```python
# Test voice recognition
from jarvis.core.enhanced_voice_recognition import get_voice_recognition_pipeline
pipeline = get_voice_recognition_pipeline()
print("✓ Voice recognition ready")

# Test task orchestration
from jarvis.core.advanced_orchestrator import get_advanced_orchestrator
orchestrator = get_advanced_orchestrator()
print("✓ Task orchestrator ready")

# Test system manager
from jarvis.core.system_manager import get_system_manager
manager = get_system_manager()
report = manager.export_report()
print("✓ System manager ready")
```

## Troubleshooting

### Python Not Found

**Problem**: "Python is not installed or not in PATH"

**Solution**:
1. Install Python from [python.org](https://www.python.org/)
2. Check "Add Python to PATH" during installation
3. Restart your terminal/PowerShell
4. Verify: `python --version`

### Permission Denied (Linux/macOS)

**Problem**: `permission denied` error

**Solution**:
```bash
# Make scripts executable
chmod +x install.sh
chmod +x ~/bin/jarvis

# Run with sudo if needed (not recommended)
sudo pip install -r requirements.txt
```

### Module Not Found

**Problem**: `ModuleNotFoundError: No module named 'jarvis'`

**Solution**:
```bash
# Ensure in correct directory
cd /path/to/Jarvis

# Reinstall
pip install -e .

# Or check if virtual environment is activated
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
```

### Import Errors

**Problem**: Dependencies not found

**Solution**:
```bash
# Upgrade pip
python -m pip install --upgrade pip

# Reinstall dependencies
pip install --force-reinstall -r requirements.txt

# Check for version conflicts
pip check
```

### Slow Installation

**Problem**: Installation is very slow

**Solution**:
```bash
# Use specific Python version
python3.10 -m pip install -r requirements.txt

# Install without extras first
pip install requests psutil numpy

# Then install rest
pip install -r requirements.txt
```

### Microphone Not Detected

**Problem**: Voice features not working

**Solution**:
```bash
# Check available audio devices
python -c "import sounddevice; print(sounddevice.query_devices())"

# Update device in .env
MICROPHONE_DEVICE=1
```

## Uninstallation

### Remove Jarvis OS

```bash
# Deactivate virtual environment (if using one)
deactivate

# Remove Jarvis package
pip uninstall jarvis-os

# Remove project directory
rm -rf /path/to/Jarvis  # Linux/macOS
rmdir /s C:\path\to\Jarvis  # Windows
```

### Clean Data

```bash
# Remove Jarvis data directory
rm -rf ~/.jarvis  # Linux/macOS
rmdir /s %USERPROFILE%\.jarvis  # Windows

# Remove .env file
rm .env
```

### Remove Virtual Environment

```bash
# Windows
rmdir /s venv

# macOS/Linux
rm -rf venv
```

## Getting Started

After installation:

1. **Read Documentation**
   - `README.md` - Project overview
   - `ENTERPRISE_INTEGRATION_GUIDE.md` - Architecture guide
   - `PHASE_1_COMPLETION_SUMMARY.md` - Features overview

2. **Configure API Keys**
   - Edit `.env` with your settings
   - Add Google Cloud API key for cloud features

3. **Start Jarvis**
   ```bash
   jarvis
   ```

4. **Try Voice Commands**
   - "Hey Jarvis, what's the time?"
   - "Jarvis, order pizza"
   - "Jarvis, check system health"

5. **Explore Examples**
   - See `examples/` directory for code samples
   - Review docstrings in source files
   - Check test files for usage patterns

## Support

- **Documentation**: See README.md and ENTERPRISE_INTEGRATION_GUIDE.md
- **Issues**: Report on GitHub
- **Questions**: Check FAQ in documentation

## License

Jarvis OS is licensed under the MIT License. See LICENSE file for details.

---

**Happy coding with Jarvis OS!** 🚀
