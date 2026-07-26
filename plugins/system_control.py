"""
J.A.R.V.I.S. System Control Plugin
Volume, brightness, WiFi, and power management.
"""

import os
import subprocess
import ctypes
from core.tool_manager import tool


# ─── Volume Control ──────────────────────────────────────────────

def _get_volume_interface():
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        try:
            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return interface.QueryInterface(IAudioEndpointVolume)

@tool(
    name="set_volume",
    description="Sets the system volume to a specific percentage (0-100).",
    parameters={
        "type": "object",
        "properties": {
            "level": {
                "type": "integer",
                "description": "Volume percentage between 0 and 100."
            }
        },
        "required": ["level"]
    }
)
def set_volume(level: int) -> str:
    try:
        level = max(0, min(100, int(level)))
        vol = _get_volume_interface()
        vol.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Volume set to {level}%."
    except Exception as e:
        return f"Failed to set volume: {e}"

@tool(
    name="mute_volume",
    description="Mutes or unmutes the system audio.",
    parameters={
        "type": "object",
        "properties": {
            "mute": {
                "type": "boolean",
                "description": "True to mute, False to unmute."
            }
        },
        "required": ["mute"]
    }
)
def mute_volume(mute: bool) -> str:
    try:
        vol = _get_volume_interface()
        vol.SetMute(mute, None)
        return "Audio muted." if mute else "Audio unmuted."
    except Exception as e:
        return f"Failed to change mute state: {e}"


# ─── Brightness Control ──────────────────────────────────────────

@tool(
    name="set_brightness",
    description="Sets the screen brightness to a specific percentage (0-100).",
    parameters={
        "type": "object",
        "properties": {
            "level": {
                "type": "integer",
                "description": "Brightness percentage between 0 and 100."
            }
        },
        "required": ["level"]
    }
)
def set_brightness(level: int) -> str:
    try:
        import screen_brightness_control as sbc
        level = max(0, min(100, int(level)))
        sbc.set_brightness(level)
        return f"Brightness set to {level}%."
    except Exception as e:
        return f"Failed to set brightness: {e}"


# ─── WiFi Control ────────────────────────────────────────────────

@tool(
    name="toggle_wifi",
    description="Enables or disables the WiFi adapter. May require administrator privileges.",
    parameters={
        "type": "object",
        "properties": {
            "enable": {
                "type": "boolean",
                "description": "True to turn WiFi on, False to turn it off."
            }
        },
        "required": ["enable"]
    }
)
def toggle_wifi(enable: bool) -> str:
    state = "enabled" if enable else "disabled"
    try:
        subprocess.run(
            ["netsh", "interface", "set", "interface", "Wi-Fi", state],
            capture_output=True, text=True, check=True
        )
        return f"WiFi has been {state}."
    except subprocess.CalledProcessError:
        return f"Couldn't change WiFi state to {state}. Run as administrator."
    except Exception as e:
        return f"Failed to toggle WiFi: {e}"


# ─── Power Management ────────────────────────────────────────────

@tool(
    name="manage_power",
    description="Performs power operations on the PC: shutdown, restart, sleep, lock, or cancel_shutdown.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["shutdown", "restart", "sleep", "lock", "cancel_shutdown"],
                "description": "The power action to perform."
            }
        },
        "required": ["action"]
    }
)
def manage_power(action: str) -> str:
    try:
        if action == "shutdown":
            os.system("shutdown /s /t 30")
            return "Computer will shut down in 30 seconds."
        elif action == "restart":
            os.system("shutdown /r /t 30")
            return "Computer will restart in 30 seconds."
        elif action == "cancel_shutdown":
            os.system("shutdown /a")
            return "Shutdown/restart cancelled."
        elif action == "sleep":
            ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)
            return "Putting computer to sleep."
        elif action == "lock":
            ctypes.windll.user32.LockWorkStation()
            return "Computer locked."
        else:
            return f"Unknown action: {action}"
    except Exception as e:
        return f"Failed to perform {action}: {e}"

@tool(
    name="get_system_status",
    description="Gets real-time CPU, RAM, Battery, and Disk usage status.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
def get_system_status() -> str:
    import psutil
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('C:\\').percent
        
        battery_str = "N/A (Desktop)"
        if hasattr(psutil, "sensors_battery"):
            battery = psutil.sensors_battery()
            if battery:
                plugged = "Plugged in" if battery.power_plugged else "Discharging"
                battery_str = f"{battery.percent}% ({plugged})"
                
        return f"CPU: {cpu}% | RAM: {ram}% | Disk (C:): {disk}% | Battery: {battery_str}"
    except Exception as e:
        return f"Failed to retrieve system status: {e}"
