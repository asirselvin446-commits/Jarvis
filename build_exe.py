import PyInstaller.__main__
import os
import shutil

# Ensure we're in the right directory
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)

print("[JARVIS] Building Executable with PyInstaller...")

PyInstaller.__main__.run([
    'main.py',
    '--name=Jarvis',
    '--windowed',              # No console window
    '--onedir',                # Single directory (faster startup than onefile)
    # ── Data files ──
    '--add-data=ui/templates;ui/templates',
    '--add-data=ui/static;ui/static',
    '--add-data=ui/mobile;ui/mobile',
    '--add-data=plugins;plugins',
    '--add-data=core;core',
    '--add-data=config.py;.',
    '--add-data=cloudflared.exe;.',
    # ── Hidden imports ──
    '--hidden-import=flask',
    '--hidden-import=webview',
    '--hidden-import=pyautogui',
    '--hidden-import=requests',
    '--hidden-import=speech_recognition',
    '--hidden-import=pyttsx3',
    '--hidden-import=pyttsx3.drivers',
    '--hidden-import=pyttsx3.drivers.sapi5',
    '--hidden-import=chromadb.telemetry.product.posthog',
    '--hidden-import=psutil',
    # ── Collect-all for tricky packages ──
    '--collect-all=chromadb',
    '--collect-all=onnxruntime',
    '--collect-all=tokenizers',
    '--collect-all=speech_recognition',
    '--collect-all=pyttsx3',
    '--collect-all=mcp',
    '--collect-all=starlette',
    '--collect-all=uvicorn',
    '--collect-all=anyio',
    '--collect-all=googleapiclient',
    '--collect-all=google_auth_oauthlib',
    # ── Build options ──
    '--distpath=dist_latest',
    '--clean',
    '-y'
])

print("[JARVIS] Build Complete! You can find Jarvis.exe in the 'dist_latest/Jarvis' folder.")
