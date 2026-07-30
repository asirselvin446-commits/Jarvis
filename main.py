"""
J.A.R.V.I.S. — Voice-Controlled Local System Assistant
═══════════════════════════════════════════════════════
Your personal AI assistant that controls your entire PC through voice commands.

Features:
    • Always-on ambient voice — say "Jarvis" to activate
    • Streaming speech recognition (faster-whisper)
    • Interruptible neural TTS (edge-tts)
    • Natural conversation with context memory
    • Multi-agent task orchestration
    • Environment-aware (gaming, meetings, presentations)

Usage:
    python main.py
"""

import sys
import os
import subprocess
import requests
import time
import logging
import threading
import pystray
from PIL import Image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("jarvis.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

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
    print("=" * 60)
    print("  J.A.R.V.I.S. Neural OS — Initializing...")
    print("=" * 60)

    start_ollama_if_needed()
    
    # Check cloud LLM availability
    from core.llm_provider import is_online, get_provider_name
    cloud_available = is_online()
    
    # Start the Flask web server in a background thread
    start_server_in_thread(port=5000)
    
    # Start the MCP SSE server in a background thread
    import threading
    from core.mcp_server import start_mcp_server
    threading.Thread(target=start_mcp_server, kwargs={"port": 8000}, daemon=True).start()

    print(f"[JARVIS] LLM Provider: {get_provider_name()}")
    print("[JARVIS] Web server started on http://127.0.0.1:5000")
    print("[JARVIS] MCP server started on http://127.0.0.1:8000")
    
    try:
        from ui.web_server import _get_pipeline
        _get_pipeline().start()
        print("[JARVIS] Voice pipeline started in background.")
    except Exception as e:
        print(f"[JARVIS] Failed to start voice pipeline: {e}")

    print("[JARVIS] Say 'Hey Jarvis' to activate voice commands.")
    print("=" * 60)
    
    # Create and start the native desktop window pointing to the local server
    window = webview.create_window(
        title="J.A.R.V.I.S. Neural OS", 
        url="http://127.0.0.1:5000",
        width=800,
        height=900,
        resizable=True
    )
    
    def on_closing():
        # When user clicks the X, hide the window instead of closing the app
        window.hide()
        return False
        
    window.events.closing += on_closing

    def setup_tray():
        def show_window(icon, item):
            window.show()

        def hide_window(icon, item):
            window.hide()

        def exit_app(icon, item):
            icon.stop()
            window.destroy()
            os._exit(0)

        tray_icon_path = os.path.join(os.path.dirname(__file__), "assets", "tray_icon.png")
        if os.path.exists(tray_icon_path):
            image = Image.open(tray_icon_path)
        else:
            # Fallback blank image
            image = Image.new('RGB', (64, 64), color=(0, 0, 0))

        menu = pystray.Menu(
            pystray.MenuItem("Show J.A.R.V.I.S.", show_window, default=True),
            pystray.MenuItem("Hide", hide_window),
            pystray.MenuItem("Quit", exit_app)
        )
        icon = pystray.Icon("JARVIS", image, "J.A.R.V.I.S. Neural OS", menu)
        
        # Run tray icon in background
        threading.Thread(target=icon.run, daemon=True).start()

    setup_tray()
    webview.start()

if __name__ == "__main__":
    main()
