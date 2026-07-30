"""
J.A.R.V.I.S. Remote Access Manager
Handles secure remote access for smartphone control.
Supports Cloudflare Tunnel for public exposure and API key auth.
"""

import os
import json
import secrets
import subprocess
import threading
from datetime import datetime

# Config storage
REMOTE_DIR = os.path.join(os.path.expanduser("~"), ".jarvis", "remote")
os.makedirs(REMOTE_DIR, exist_ok=True)
AUTH_FILE = os.path.join(REMOTE_DIR, "auth_config.json")


def _load_auth_config() -> dict:
    """Load or create auth configuration."""
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass

    # Generate new API key on first run
    config = {
        "api_key": secrets.token_urlsafe(32),
        "created_at": datetime.now().isoformat(),
        "enabled": True
    }
    with open(AUTH_FILE, "w") as f:
        json.dump(config, f, indent=2)

    print(f"[RemoteAccess] Generated new API key: {config['api_key']}")
    return config


def _save_auth_config(config: dict):
    with open(AUTH_FILE, "w") as f:
        json.dump(config, f, indent=2)


AUTH_CONFIG = _load_auth_config()


def get_api_key() -> str:
    """Get the current API key for remote access."""
    return AUTH_CONFIG.get("api_key", "")


def verify_api_key(key: str) -> bool:
    """Verify an API key against the stored key."""
    return key == AUTH_CONFIG.get("api_key", "") and AUTH_CONFIG.get("enabled", False)


def regenerate_api_key() -> str:
    """Generate a new API key and invalidate the old one."""
    AUTH_CONFIG["api_key"] = secrets.token_urlsafe(32)
    AUTH_CONFIG["created_at"] = datetime.now().isoformat()
    _save_auth_config(AUTH_CONFIG)
    return AUTH_CONFIG["api_key"]


# ─── Cloudflare Tunnel ───────────────────────────────────────────

_tunnel_process = None


def start_cloudflare_tunnel(port: int = 8000) -> str:
    """
    Start a Cloudflare Quick Tunnel to expose the MCP server publicly.
    No account needed — uses cloudflared's free quick tunnels.
    
    Returns the public URL.
    """
    global _tunnel_process

    if _tunnel_process and _tunnel_process.poll() is None:
        return "Tunnel is already running."

    # Look for local cloudflared.exe in the parent directory of core/
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_exe = os.path.join(base_dir, "cloudflared.exe")
    cmd_name = local_exe if os.path.exists(local_exe) else "cloudflared"

    try:
        # Check if cloudflared is installed
        check = subprocess.run(
            [cmd_name, "--version"],
            capture_output=True, text=True, timeout=5
        )
        if check.returncode != 0:
            return ("cloudflared not installed. Install with:\n"
                    "  winget install Cloudflare.cloudflared")
    except FileNotFoundError:
        return ("cloudflared not installed. Install with:\n"
                "  winget install Cloudflare.cloudflared")

    # Start the tunnel
    _tunnel_process = subprocess.Popen(
        [cmd_name, "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )

    # Wait for the URL to appear in stderr
    import time
    url = None
    for _ in range(30):  # Wait up to 15 seconds
        line = _tunnel_process.stderr.readline()
        if "trycloudflare.com" in line:
            import re
            match = re.search(r'https://[^\s]+\.trycloudflare\.com', line)
            if match:
                url = match.group(0)
                break
        time.sleep(0.5)

    if url:
        # Save tunnel URL
        tunnel_info = {
            "url": url,
            "mcp_sse": f"{url}/sse",
            "api_key": AUTH_CONFIG["api_key"],
            "started_at": datetime.now().isoformat()
        }
        with open(os.path.join(REMOTE_DIR, "tunnel_info.json"), "w") as f:
            json.dump(tunnel_info, f, indent=2)

        print(f"[RemoteAccess] Tunnel started: {url}")
        return f"Tunnel active!\n  URL: {url}\n  MCP: {url}/sse\n  API Key: {AUTH_CONFIG['api_key']}"
    else:
        return "Tunnel started but couldn't detect URL. Check cloudflared logs."


def stop_cloudflare_tunnel() -> str:
    """Stop the Cloudflare tunnel."""
    global _tunnel_process
    if _tunnel_process and _tunnel_process.poll() is None:
        _tunnel_process.terminate()
        _tunnel_process = None
        return "Cloudflare tunnel stopped."
    return "No tunnel is running."


def get_tunnel_status() -> str:
    """Check if the tunnel is running."""
    if _tunnel_process and _tunnel_process.poll() is None:
        info_path = os.path.join(REMOTE_DIR, "tunnel_info.json")
        if os.path.exists(info_path):
            with open(info_path, "r") as f:
                info = json.load(f)
            return f"Tunnel running: {info.get('url', 'unknown')}"
        return "Tunnel is running."
    return "No tunnel is running."
