@echo off
REM Jarvis OS Uninstaller for Windows

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║                                                            ║
echo ║        Jarvis OS Uninstaller                               ║
echo ║                                                            ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

echo Are you sure you want to uninstall Jarvis OS?
echo This will:
echo - Remove Jarvis package
echo - Remove Python dependencies (if you choose)
echo - Keep configuration files in %%USERPROFILE%%\.jarvis
echo.
echo (Y/n)
set /p CHOICE=
if /i "%CHOICE%"=="n" (
    echo Uninstallation cancelled.
    exit /b 0
)

echo.
echo [*] Uninstalling Jarvis OS...

REM Uninstall Jarvis package
pip uninstall -y jarvis-os
if errorlevel 1 (
    echo [!] Warning: Could not uninstall jarvis-os package
)

REM Ask to remove dependencies
echo.
echo Do you want to remove Python dependencies as well? (y/N)
set /p DEP_CHOICE=
if /i "%DEP_CHOICE%"=="y" (
    echo [*] Removing dependencies...
    pip uninstall -y -r requirements.txt
    echo [+] Dependencies removed
)

REM Remove desktop shortcut
echo [*] Removing desktop shortcuts...
if exist "%USERPROFILE%\Desktop\Jarvis.bat" (
    del "%USERPROFILE%\Desktop\Jarvis.bat"
    echo [+] Removed Jarvis.bat from desktop
)

REM Keep .jarvis directory
echo.
echo [*] Configuration and data files kept at:
echo     %USERPROFILE%\.jarvis
echo.
echo To remove them manually, run:
echo     rmdir /s %USERPROFILE%\.jarvis
echo.

echo ╔════════════════════════════════════════════════════════════╗
echo ║                                                            ║
echo ║        Uninstallation Complete                             ║
echo ║                                                            ║
echo ║  Your configuration is preserved at:                      ║
echo ║  %USERPROFILE%\.jarvis                     ║
echo ║                                                            ║
echo ║  To reinstall:                                             ║
echo ║  pip install jarvis-os                                     ║
echo ║                                                            ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

pause
