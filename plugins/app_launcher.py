"""
J.A.R.V.I.S. App Launcher Plugin
Auto-discovers and launches Windows applications.
"""

import os
import subprocess
import shutil
import glob
import json
import psutil
import winreg
from difflib import get_close_matches

from core.tool_manager import tool
from config import APP_PATHS

# Global caches
_APP_CACHE = {}
_UWP_CACHE = None

def _find_app(app_name: str) -> str | None:
    """Smart app discovery logic."""
    global _UWP_CACHE
    
    name_lower = app_name.lower().strip()
    for suffix in [" player", " app", " program", " application"]:
        if name_lower.endswith(suffix):
            name_lower = name_lower[:-len(suffix)].strip()

    if name_lower in APP_PATHS:
        path = APP_PATHS[name_lower]
        if path.startswith("ms-") or path.endswith(".msc") or os.path.exists(path):
            return path

    matches = get_close_matches(name_lower, APP_PATHS.keys(), n=1, cutoff=0.6)
    if matches:
        path = APP_PATHS[matches[0]]
        if path.startswith("ms-") or path.endswith(".msc") or os.path.exists(path):
            return path

    if name_lower in _APP_CACHE:
        return _APP_CACHE[name_lower]

    # ... Simplified discovery to save space for the plugin ...
    for exe_name in [name_lower, f"{name_lower}.exe"]:
        found = shutil.which(exe_name)
        if found:
            _APP_CACHE[name_lower] = found
            return found

    # UWP search
    if _UWP_CACHE is None:
        _UWP_CACHE = {}
        try:
            result = subprocess.run(
                ["powershell", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
                capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0 and result.stdout.strip():
                apps = json.loads(result.stdout.strip())
                for app in apps:
                    name = app.get("Name", "").lower()
                    appid = app.get("AppID", "")
                    if name and appid:
                        _UWP_CACHE[name] = appid
        except Exception:
            _UWP_CACHE = {}
            
    if name_lower in _UWP_CACHE:
        return f"explorer shell:AppsFolder\\{_UWP_CACHE[name_lower]}"
        
    for name, appid in _UWP_CACHE.items():
        if name_lower in name:
            return f"explorer shell:AppsFolder\\{appid}"
            
    return None

@tool(
    name="open_application",
    description="Opens or launches a desktop application or program by name (e.g., 'chrome', 'spotify', 'notepad'). Do NOT use for websites.",
    parameters={
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "The name of the application to open."
            }
        },
        "required": ["app_name"]
    }
)
def open_application(app_name: str) -> str:
    app_path = _find_app(app_name)
    if app_path:
        try:
            if app_path.startswith("ms-") or app_path.endswith(".lnk"):
                os.startfile(app_path)
            elif app_path.startswith("explorer shell:AppsFolder") or (" " in app_path and "--" in app_path):
                subprocess.Popen(app_path, shell=True)
            else:
                subprocess.Popen(app_path)
            return f"Successfully opened {app_name}."
        except Exception as e:
            return f"Found {app_name} but failed to open: {e}"

    try:
        os.startfile(app_name)
        return f"Successfully opened {app_name} via OS default."
    except Exception:
        return f"Could not find or open application named '{app_name}'."


@tool(
    name="close_application",
    description="Closes or kills a running desktop application by name.",
    parameters={
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "The name of the application to close."
            }
        },
        "required": ["app_name"]
    }
)
def close_application(app_name: str) -> str:
    app_name = app_name.lower().strip()
    killed = False
    for proc in psutil.process_iter(["name"]):
        try:
            proc_name = proc.info["name"].lower()
            if app_name in proc_name or proc_name.replace(".exe", "") == app_name:
                proc.terminate()
                killed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
            
    if killed:
        return f"Successfully closed {app_name}."
    return f"Could not find {app_name} running."
