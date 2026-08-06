# Jarvis OS Distribution & Packaging Guide

This guide explains how to distribute Jarvis OS to end users as installers and packages.

## Distribution Methods

### 1. PyPI Package (Recommended for Developers)

**Publish to Python Package Index:**

```bash
# Install build tools
pip install build twine

# Build distribution
python -m build

# Upload to PyPI
twine upload dist/*
```

**Users install with:**
```bash
pip install jarvis-os
```

### 2. Standalone Installer (Windows)

**Create MSI/EXE installer using PyInstaller:**

```bash
# Install PyInstaller
pip install pyinstaller

# Build executable
pyinstaller --onedir --windowed --icon=logo.ico jarvis/cli.py

# Create installer with NSIS
# (Requires NSIS installation from nsis.sourceforge.io)
makensis installer.nsi
```

**Distribution**: Users download `.msi` or `.exe` and double-click to install.

### 3. Homebrew Package (macOS)

Create formula:
```ruby
class JarvisOs < Formula
  desc "Enterprise AI agent platform"
  homepage "https://github.com/asirselvin446-commits/Jarvis"
  url "https://github.com/asirselvin446-commits/Jarvis/archive/v1.0.0.tar.gz"
  sha256 "XXXXXXXX"
  
  depends_on "python@3.10"
  
  def install
    virtualenv_install_with_resources
  end
end
```

**Users install with:**
```bash
brew install jarvis-os
```

### 4. Snap Package (Linux)

Create `snapcraft.yaml`:
```yaml
name: jarvis-os
version: '1.0.0'
description: 'Enterprise AI agent platform'

parts:
  jarvis:
    plugin: python
    source: .
    requirements: [requirements.txt]

apps:
  jarvis:
    command: jarvis
```

**Build and publish:**
```bash
snapcraft
snapcraft push jarvis-os_1.0.0_amd64.snap --release=stable
```

**Users install with:**
```bash
snap install jarvis-os
```

### 5. Docker Container

**Dockerfile:**
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN pip install -e .

ENV JARVIS_DATA_DIR=/data
VOLUME ["/data"]

ENTRYPOINT ["jarvis"]
```

**Build and run:**
```bash
docker build -t jarvis-os:1.0.0 .
docker push myregistry/jarvis-os:1.0.0
```

**Users run with:**
```bash
docker run -it myregistry/jarvis-os:1.0.0
```

## Creating Windows MSI Installer

### Step 1: Create WiX Configuration

**jarvis.wxs:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
    <Product Id="*" Name="Jarvis OS" Language="1033" Version="1.0.0.0" UpgradeCode="GUID">
        <Package InstallerVersion="200" Compressed="yes" />
        <Media Id="1" Cabinet="jarvis.cab" EmbedCab="yes" />
        
        <Feature Id="ProductFeature" Title="Jarvis OS" Level="1">
            <ComponentRef Id="MainExecutable" />
            <ComponentRef Id="PythonFiles" />
        </Feature>
    </Product>
</Wix>
```

### Step 2: Build

```bash
# Install WiX Toolset
choco install wixtoolset

# Compile
candle.exe jarvis.wxs
light.exe jarvis.wixobj -out jarvis.msi
```

## Package Contents

### Minimum Files
```
jarvis-os/
├── setup.py
├── pyproject.toml
├── requirements.txt
├── README.md
├── INSTALL.md
├── QUICK_INSTALL.md
├── install.bat
├── install.ps1
├── install.sh
├── uninstall.bat
├── jarvis/
│   ├── __init__.py
│   ├── cli.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── voice_orchestrator.py
│   │   ├── universal_executor.py
│   │   └── ...
│   └── plugins/
└── config/
    └── settings.json.template
```

### Documentation
```
docs/
├── ENTERPRISE_INTEGRATION_GUIDE.md
├── PHASE_1_COMPLETION_SUMMARY.md
├── INSTALL.md
├── QUICK_INSTALL.md
└── examples/
    └── voice_example.py
```

## Versioning

Use Semantic Versioning: **MAJOR.MINOR.PATCH**

```
1.0.0       - Initial release
1.1.0       - New features (backward compatible)
1.0.1       - Bug fixes
2.0.0       - Breaking changes
```

Update in:
- `setup.py`: `version="1.0.0"`
- `pyproject.toml`: `version = "1.0.0"`
- Git tag: `git tag -a v1.0.0 -m "Release 1.0.0"`

## Release Checklist

- [ ] Update version numbers
- [ ] Update CHANGELOG.md
- [ ] Run tests: `pytest`
- [ ] Check linting: `flake8 jarvis/`
- [ ] Build package: `python -m build`
- [ ] Test installation: `pip install dist/jarvis_os-1.0.0-py3-none-any.whl`
- [ ] Create git tag: `git tag v1.0.0`
- [ ] Push to GitHub: `git push --tags`
- [ ] Upload to PyPI: `twine upload dist/*`
- [ ] Create GitHub release with notes
- [ ] Update website/documentation

## Installer Verification

### Test Installation Workflow

```bash
# 1. Test on clean environment
python -m venv test_env
source test_env/bin/activate

# 2. Install from package
pip install jarvis-os

# 3. Verify
jarvis --version
jarvis --help

# 4. Run tests
pytest tests/

# 5. Cleanup
deactivate
rm -rf test_env
```

### Test on Multiple Platforms

- Windows 10, 11
- macOS 10.14+
- Ubuntu 18.04+, 20.04+, 22.04+
- Fedora, Arch, others

## Hosting & Distribution

### PyPI
- URL: https://pypi.org/project/jarvis-os/
- Built-in Python package manager
- Automatic dependency resolution

### GitHub Releases
- Upload installers (`.exe`, `.msi`, `.dmg`, `.tar.gz`)
- Add release notes
- Notify users

### Website
- Create project website
- Provide download links
- Installation instructions
- Screenshots, features, pricing (if applicable)

### Docker Hub
- Push Docker images
- Document usage
- Provide docker-compose examples

## Update Strategy

### Auto-Update (Recommended)
```python
def check_for_updates():
    latest = get_latest_version()
    current = get_current_version()
    
    if latest > current:
        print(f"Update available: {latest}")
        return True
    return False
```

### Manual Update
```bash
pip install --upgrade jarvis-os
```

## License & Legal

- Include LICENSE file (MIT recommended)
- Update CONTRIBUTORS.md
- Add copyright notices
- Ensure compliance with dependencies' licenses

## Distribution Statistics

Track:
- Downloads per version
- Installation success rate
- Common issues
- User feedback

Use services like:
- PyPI statistics
- GitHub releases analytics
- Docker Hub insights

---

## Quick Distribution Commands

```bash
# Build local
python -m build

# Test locally
pip install -e .

# Upload to PyPI (requires authentication)
twine upload dist/*

# Create GitHub release
gh release create v1.0.0 dist/* --notes "Release notes here"

# Push Docker image
docker tag jarvis-os:latest myregistry/jarvis-os:1.0.0
docker push myregistry/jarvis-os:1.0.0
```

---

**Ready to distribute Jarvis OS to the world!** 🚀
