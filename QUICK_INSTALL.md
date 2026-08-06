# Jarvis OS - Installation Quick Reference

## One-Line Installation

### Windows (PowerShell)
```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope CurrentUser -Force; .\install.ps1
```

### Windows (Batch)
```batch
install.bat
```

### macOS/Linux (Bash)
```bash
chmod +x install.sh && ./install.sh
```

### Any Platform (Pip)
```bash
pip install -r requirements.txt
pip install -e .
```

---

## Installation Steps (Manual)

### 1. Prerequisites
```bash
# Check Python (3.8+)
python --version

# Check pip
pip --version
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Install Jarvis
```bash
pip install -e .
```

### 4. Verify
```bash
python -c "import jarvis; print('✓ Installed')"
```

---

## Configuration

### 1. Create .env file
```bash
# Windows
echo GOOGLE_API_KEY=your_key > .env
echo OLLAMA_URL=http://localhost:11434 >> .env

# macOS/Linux
cat > .env << EOF
GOOGLE_API_KEY=your_key
OLLAMA_URL=http://localhost:11434
EOF
```

### 2. Run Setup Wizard
```bash
jarvis-setup
```

---

## Common Commands

```bash
# Start Jarvis
jarvis

# Configuration
jarvis-config

# Help
jarvis --help

# Version
jarvis --version
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Python not found | Install from [python.org](https://www.python.org/) |
| Module not found | Run `pip install -e .` |
| Permissions error | Run as Administrator/with sudo |
| Slow install | Try: `pip install --no-cache-dir -r requirements.txt` |
| Audio issues | Update sounddevice: `pip install --upgrade sounddevice` |

---

## Post-Installation

1. **Set API Keys** in `.env`
2. **Run Config Wizard**: `jarvis-config`
3. **Start Jarvis**: `jarvis`
4. **Read Docs**: `ENTERPRISE_INTEGRATION_GUIDE.md`

---

## Uninstall

### Windows
```batch
uninstall.bat
```

### macOS/Linux
```bash
pip uninstall jarvis-os
rm -rf ~/.jarvis
```

---

## Need Help?

- **Documentation**: See `INSTALL.md`
- **Architecture**: See `ENTERPRISE_INTEGRATION_GUIDE.md`
- **Features**: See `PHASE_1_COMPLETION_SUMMARY.md`
- **README**: See `README.md`

---

**Jarvis OS v1.0.0** - Enterprise AI Agent Platform 🚀
