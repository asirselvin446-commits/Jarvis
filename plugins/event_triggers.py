"""
J.A.R.V.I.S. Event Triggers Plugin
Monitors system events and triggers automated actions.
Supports: WiFi connect/disconnect, USB device plug, time-of-day triggers,
battery thresholds, and process start/stop monitoring.
"""

import os
import json
import time
import threading
import subprocess
from datetime import datetime
from core.tool_manager import tool, _TOOL_REGISTRY

# Storage path for triggers
TRIGGERS_DIR = os.path.join(os.path.expanduser("~"), ".jarvis", "triggers")
os.makedirs(TRIGGERS_DIR, exist_ok=True)

# Global state for the event monitor
_monitor_thread = None
_monitor_running = False
_active_triggers = []
_trigger_lock = threading.Lock()

# Track previous state for change detection
_prev_state = {
    "wifi_connected": None,
    "battery_level": None,
    "battery_plugged": None,
    "running_processes": set(),
}


def _get_wifi_status() -> bool:
    """Check if WiFi is connected."""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, timeout=5
        )
        return "connected" in result.stdout.lower() and "not connected" not in result.stdout.lower()
    except Exception:
        return False


def _get_battery_info() -> dict:
    """Get battery level and plugged status."""
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery:
            return {"level": battery.percent, "plugged": battery.power_plugged}
    except Exception:
        pass
    return {"level": 100, "plugged": True}


def _is_process_running(process_name: str) -> bool:
    """Check if a specific process is running."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        return process_name.lower() in result.stdout.lower()
    except Exception:
        return False


def _execute_trigger_action(trigger: dict):
    """Execute the action associated with a trigger."""
    action_tool = trigger.get("action_tool")
    action_args = trigger.get("action_args", {})

    if action_tool and action_tool in _TOOL_REGISTRY:
        try:
            func = _TOOL_REGISTRY[action_tool]["func"]
            result = func(**action_args)
            print(f"[EventTrigger] Fired '{trigger['name']}' -> {action_tool}: {str(result)[:100]}")
        except Exception as e:
            print(f"[EventTrigger] Error executing trigger '{trigger['name']}': {e}")
    else:
        print(f"[EventTrigger] Unknown tool '{action_tool}' for trigger '{trigger['name']}'")


def _event_monitor_loop():
    """Background loop that checks for event triggers."""
    global _monitor_running, _prev_state

    print("[EventTrigger] Monitor started.")

    while _monitor_running:
        try:
            # Get current state
            wifi_connected = _get_wifi_status()
            battery_info = _get_battery_info()

            with _trigger_lock:
                triggers = list(_active_triggers)

            for trigger in triggers:
                event_type = trigger.get("event_type")

                if event_type == "wifi_connect" and wifi_connected and not _prev_state.get("wifi_connected"):
                    _execute_trigger_action(trigger)

                elif event_type == "wifi_disconnect" and not wifi_connected and _prev_state.get("wifi_connected"):
                    _execute_trigger_action(trigger)

                elif event_type == "battery_low":
                    threshold = trigger.get("threshold", 20)
                    if battery_info["level"] <= threshold and (
                        _prev_state.get("battery_level") is None or
                        _prev_state["battery_level"] > threshold
                    ):
                        _execute_trigger_action(trigger)

                elif event_type == "battery_charging":
                    if battery_info["plugged"] and not _prev_state.get("battery_plugged"):
                        _execute_trigger_action(trigger)

                elif event_type == "process_start":
                    process = trigger.get("process_name", "")
                    if process and _is_process_running(process):
                        if process.lower() not in _prev_state.get("running_processes", set()):
                            _execute_trigger_action(trigger)
                            _prev_state.setdefault("running_processes", set()).add(process.lower())

                elif event_type == "process_stop":
                    process = trigger.get("process_name", "")
                    if process and not _is_process_running(process):
                        if process.lower() in _prev_state.get("running_processes", set()):
                            _execute_trigger_action(trigger)
                            _prev_state.get("running_processes", set()).discard(process.lower())

            # Update previous state
            _prev_state["wifi_connected"] = wifi_connected
            _prev_state["battery_level"] = battery_info["level"]
            _prev_state["battery_plugged"] = battery_info["plugged"]

        except Exception as e:
            print(f"[EventTrigger] Monitor error: {e}")

        time.sleep(10)  # Check every 10 seconds

    print("[EventTrigger] Monitor stopped.")


def _start_monitor():
    """Start the event monitor background thread."""
    global _monitor_thread, _monitor_running
    if _monitor_running:
        return
    _monitor_running = True
    _monitor_thread = threading.Thread(target=_event_monitor_loop, daemon=True)
    _monitor_thread.start()


def _stop_monitor():
    """Stop the event monitor."""
    global _monitor_running
    _monitor_running = False


def _save_triggers():
    """Save all active triggers to disk."""
    path = os.path.join(TRIGGERS_DIR, "active_triggers.json")
    with _trigger_lock:
        serializable = []
        for t in _active_triggers:
            serializable.append({k: v for k, v in t.items()})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)


def _load_triggers():
    """Load triggers from disk."""
    global _active_triggers
    path = os.path.join(TRIGGERS_DIR, "active_triggers.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                _active_triggers = json.load(f)
        except Exception:
            _active_triggers = []


# Load triggers on import
_load_triggers()
if _active_triggers:
    _start_monitor()


# ─── Tools ───────────────────────────────────────────────────────

@tool(
    name="create_event_trigger",
    description=(
        "Creates an automated event trigger. When the specified event occurs, "
        "the specified tool will be executed automatically. "
        "Supported events: 'wifi_connect', 'wifi_disconnect', 'battery_low', "
        "'battery_charging', 'process_start', 'process_stop'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name for this trigger (e.g., 'open_slack_on_wifi')."
            },
            "event_type": {
                "type": "string",
                "enum": ["wifi_connect", "wifi_disconnect", "battery_low",
                         "battery_charging", "process_start", "process_stop"],
                "description": "The event to watch for."
            },
            "action_tool": {
                "type": "string",
                "description": "The tool to execute when the event fires (e.g., 'open_application')."
            },
            "action_args": {
                "type": "object",
                "description": "Arguments to pass to the action tool (e.g., {\"app_name\": \"slack\"})."
            },
            "process_name": {
                "type": "string",
                "description": "For process_start/stop events: the process name to watch (e.g., 'chrome.exe').",
                "default": ""
            },
            "threshold": {
                "type": "integer",
                "description": "For battery_low events: the battery percentage threshold.",
                "default": 20
            }
        },
        "required": ["name", "event_type", "action_tool", "action_args"]
    }
)
def create_event_trigger(name: str, event_type: str, action_tool: str,
                         action_args: dict, process_name: str = "",
                         threshold: int = 20) -> str:
    trigger = {
        "name": name,
        "event_type": event_type,
        "action_tool": action_tool,
        "action_args": action_args,
        "process_name": process_name,
        "threshold": threshold,
        "created_at": datetime.now().isoformat()
    }

    with _trigger_lock:
        # Remove existing trigger with same name
        _active_triggers[:] = [t for t in _active_triggers if t.get("name") != name]
        _active_triggers.append(trigger)

    _save_triggers()
    _start_monitor()

    return f"Event trigger '{name}' created: On '{event_type}' → execute '{action_tool}'."


@tool(
    name="list_event_triggers",
    description="Lists all active event triggers.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
def list_event_triggers() -> str:
    with _trigger_lock:
        if not _active_triggers:
            return "No active event triggers."

        lines = []
        for t in _active_triggers:
            lines.append(
                f"  • {t['name']}: on '{t['event_type']}' → {t['action_tool']}({t['action_args']})"
            )
        return f"Active triggers ({len(_active_triggers)}):\n" + "\n".join(lines)


@tool(
    name="delete_event_trigger",
    description="Deletes an event trigger by name.",
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the trigger to delete."
            }
        },
        "required": ["name"]
    }
)
def delete_event_trigger(name: str) -> str:
    with _trigger_lock:
        before = len(_active_triggers)
        _active_triggers[:] = [t for t in _active_triggers if t.get("name") != name]
        after = len(_active_triggers)

    if before == after:
        return f"Trigger '{name}' not found."

    _save_triggers()

    # Stop monitor if no triggers left
    if not _active_triggers:
        _stop_monitor()

    return f"Trigger '{name}' deleted."
