"""
J.A.R.V.I.S. — Voice-Controlled Local System Assistant
═══════════════════════════════════════════════════════
Your personal AI assistant that controls your entire PC through voice commands.

Usage:
    python main.py

Features:
    • Voice recognition (Google Speech API)
    • Text-to-speech responses (SAPI5)
    • Open/close/switch applications
    • Control volume, brightness, WiFi
    • Google/YouTube search
    • Media playback controls
    • Screenshots
    • System info (battery, CPU, RAM)
    • Shutdown, restart, sleep, lock
    • Beautiful dark-themed UI with animated waveform
"""

import sys
import os
import subprocess
import requests
import time

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import webview
from ui.web_server import start_server_in_thread

def start_ollama_if_needed():
    """Starts the Ollama server in the background if it's not already running."""
    try:
        requests.get("http://localhost:11434/api/tags", timeout=1)
    except requests.ConnectionError:
        print("[JARVIS] Starting Ollama server in the background...")
        try:
            # Start Ollama hidden
            subprocess.Popen(
                ["ollama", "serve"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(2)  # Give it a moment to start
        except Exception as e:
            print(f"[JARVIS] Failed to start Ollama automatically: {e}")

def main():
    start_ollama_if_needed()
    
    # Start the Flask web server in a background thread
    start_server_in_thread(port=5000)
    
    # Create and start the native desktop window pointing to the local server
    webview.create_window(
        title="J.A.R.V.I.S. Neural OS", 
        url="http://127.0.0.1:5000",
        width=800,
        height=900,
        resizable=True
    )
    webview.start()

if __name__ == "__main__":
    main()
