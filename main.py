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
import logging.handlers
import threading
import signal
import pystray
from PIL import Image

import config

# ─── Logging with rotation ────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            config.LOG_FILE,
            maxBytes=config.LOG_MAX_BYTES,
            backupCount=config.LOG_BACKUP_COUNT,
            encoding="utf-8",
        ),
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

# ─── Global references for graceful shutdown ──────────────────────
_kernel = None
_window = None
_tray_icon = None


def _check_and_prompt_api_key():
    """Ensures a Google Gemini API key is configured; prompts user if missing."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        # Check user config directory
        user_env = os.path.join(os.path.expanduser("~"), ".jarvis", "config", ".env")
        if os.path.exists(user_env):
            from dotenv import load_dotenv
            load_dotenv(user_env)
            api_key = os.environ.get("GOOGLE_API_KEY")

    if not api_key:
        print("[JARVIS] No GOOGLE_API_KEY found. Launching API Onboarding Setup...")
        try:
            from installer.ui.onboarding_wizard import launch_standalone_wizard
            launch_standalone_wizard()
            # Reload env after wizard saves
            from dotenv import load_dotenv
            load_dotenv(override=True)
        except Exception as e:
            print(f"[JARVIS] Could not launch onboarding GUI ({e}). Please configure GOOGLE_API_KEY in .env")


def _graceful_shutdown():
    """Perform a clean shutdown: stop services, flush DBs, release resources."""
    global _kernel, _tray_icon

    print("[JARVIS] Initiating graceful shutdown...")

    # 1. Stop voice pipeline
    try:
        from ui.web_server import _get_pipeline
        pipeline = _get_pipeline()
        if pipeline and pipeline.is_running:
            pipeline.stop()
            print("[JARVIS] Voice pipeline stopped.")
    except Exception as e:
        print(f"[JARVIS] Voice pipeline shutdown error: {e}")

    # 2. Shut down the OS kernel (saves state, flushes memory)
    try:
        if _kernel:
            _kernel.shutdown()
            print("[JARVIS] OS kernel shut down.")
    except Exception as e:
        print(f"[JARVIS] Kernel shutdown error: {e}")

    # 2.1 Stop Screen Monitor
    try:
        from core.screen_monitor import get_screen_monitor
        sm = get_screen_monitor(auto_start=False)
        if sm and sm.is_running:
            sm.stop()
            print("[JARVIS] Screen monitor stopped.")
    except Exception:
        pass

    # 3. Close memory database connections
    try:
        from core.memory import MemoryManager
        # The singleton MemoryManager in _kernel will be closed via kernel.shutdown()
    except Exception:
        pass

    # 4. Stop tray icon
    try:
        if _tray_icon:
            _tray_icon.stop()
    except Exception:
        pass

    # 5. Flush log handlers
    for handler in logging.root.handlers:
        try:
            handler.flush()
            handler.close()
        except Exception:
            pass

    print("[JARVIS] Graceful shutdown complete.")


def _signal_handler(signum, frame):
    """Handle SIGINT/SIGTERM for clean shutdown."""
    print(f"\n[JARVIS] Received signal {signum}, shutting down...")
    _graceful_shutdown()
    sys.exit(0)


def main():
    global _kernel, _window, _tray_icon

    # Register signal handlers for clean Ctrl+C
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    print("=" * 60)
    print(f"  J.A.R.V.I.S. Neural OS v{config.VERSION} — Initializing...")
    print("=" * 60)

    # Check / Prompt for Cloud API key on startup
    _check_and_prompt_api_key()

    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        try:
            resp = requests.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                timeout=3
            )
            if resp.status_code == 200:
                print("[JARVIS] Cloud Gemini API connected successfully (Fast Cloud Intelligence)")
            else:
                print("[JARVIS] Warning: Google API key check returned status", resp.status_code)
        except Exception:
            print("[JARVIS] Cloud connectivity check skipped (offline or network issue)")
    else:
        print("[JARVIS] Warning: Running without GOOGLE_API_KEY. Configure in Settings.")
    
    # Check cloud LLM availability
    from core.llm_provider import is_online, get_provider_name
    cloud_available = is_online()
    
    # Start the Flask web server in a background thread
    start_server_in_thread(port=config.WEB_SERVER_PORT)
    
    # Start the MCP SSE server in a background thread
    from core.mcp_server import start_mcp_server
    threading.Thread(target=start_mcp_server, kwargs={"port": config.MCP_SERVER_PORT}, daemon=True).start()

    print(f"[JARVIS] LLM Provider: {get_provider_name()}")
    print(f"[JARVIS] Web server started on http://127.0.0.1:{config.WEB_SERVER_PORT}")
    print(f"[JARVIS] MCP server started on http://127.0.0.1:{config.MCP_SERVER_PORT}")
    
    try:
        from ui.web_server import _get_pipeline, _get_kernel
        _kernel = _get_kernel()
        _get_pipeline().start()
        print("[JARVIS] Voice pipeline started in background.")
    except Exception as e:
        print(f"[JARVIS] Failed to start voice pipeline: {e}")

    # Vision agent memory loop is now started automatically by the Agent Society

    try:
        from core.observer import _observer
        from ui.web_server import _get_pipeline
        _observer.voice_pipeline = _get_pipeline()
        _observer.start()
        print("[JARVIS] Observer Agent started in background.")
    except Exception as e:
        print(f"[JARVIS] Failed to start Observer Agent: {e}")

    try:
        from core.telegram_bridge import _telegram_bridge
        _telegram_bridge.start()
        print("[JARVIS] Telegram Bridge started in background.")
    except Exception as e:
        print(f"[JARVIS] Failed to start Telegram Bridge: {e}")

    try:
        from core.desktop_monitor import get_desktop_monitor
        get_desktop_monitor().start()
    except Exception as e:
        print(f"[JARVIS] Failed to start Desktop Monitor: {e}")

    try:
        from core.proactive_intelligence import get_proactive_intelligence
        get_proactive_intelligence().start()
    except Exception as e:
        print(f"[JARVIS] Failed to start Proactive Intelligence: {e}")

    try:
        from core.whatsapp_watcher import get_whatsapp_watcher
        get_whatsapp_watcher().start()
    except Exception as e:
        print(f"[JARVIS] Failed to start WhatsApp Watcher: {e}")

    try:
        from core.email_watcher import get_email_watcher
        get_email_watcher().start()
    except Exception as e:
        print(f"[JARVIS] Failed to start Email Watcher: {e}")

    try:
        from core.screen_monitor import get_screen_monitor
        get_screen_monitor(auto_start=True)
        print("[JARVIS] Continuous Screen Monitor & Visual Intelligence started.")
    except Exception as e:
        print(f"[JARVIS] Failed to start Screen Monitor: {e}")


    print("[JARVIS] Say 'Hey Jarvis' to activate voice commands.")
    print("=" * 60)
    
    # Create and start the native desktop window pointing to the local server
    _window = webview.create_window(
        title=f"J.A.R.V.I.S. Neural OS v{config.VERSION} — Mark VIII Command Center", 
        url=f"http://127.0.0.1:{config.WEB_SERVER_PORT}",
        width=1380,
        height=880,
        min_size=(960, 680),
        resizable=True,
        background_color="#070b14"
    )
    
    def on_closing():
        # When user clicks the X, hide the window instead of closing the app
        _window.hide()
        return False
        
    _window.events.closing += on_closing

    def setup_tray():
        global _tray_icon

        def show_window(icon, item):
            _window.show()

        def hide_window(icon, item):
            _window.hide()

        def exit_app(icon, item):
            _graceful_shutdown()
            _window.destroy()
            sys.exit(0)

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
        _tray_icon = pystray.Icon("JARVIS", image, "J.A.R.V.I.S. Neural OS", menu)
        
        # Run tray icon in background
        threading.Thread(target=_tray_icon.run, daemon=True).start()

    setup_tray()
    webview.start()

if __name__ == "__main__":
    main()

