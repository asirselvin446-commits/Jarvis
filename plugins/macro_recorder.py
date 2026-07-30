"""
J.A.R.V.I.S. Macro Recorder Plugin
Records sequences of tool calls as named macros, saves them to disk,
and replays them on voice command. Supports listing and deleting macros.
"""

import os
import json
import time
import threading
from datetime import datetime
from core.tool_manager import tool, _TOOL_REGISTRY

# Storage path for macros
MACROS_DIR = os.path.join(os.path.expanduser("~"), ".jarvis", "macros")
os.makedirs(MACROS_DIR, exist_ok=True)

# In-memory recording state
_recording = False
_current_recording = []
_current_macro_name = ""
_recording_lock = threading.Lock()


def _get_macro_path(name: str) -> str:
    """Get the file path for a named macro."""
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return os.path.join(MACROS_DIR, f"{safe_name}.json")


def _load_macro(name: str) -> dict | None:
    """Load a macro from disk."""
    path = _get_macro_path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_macro(name: str, steps: list):
    """Save a macro to disk."""
    macro = {
        "name": name,
        "steps": steps,
        "created_at": datetime.now().isoformat(),
        "step_count": len(steps)
    }
    path = _get_macro_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(macro, f, indent=2)


# ─── Hook into ToolManager to intercept tool calls during recording ──

_original_execute = None


def _recording_execute_hook(name: str, arguments: dict):
    """Intercept tool calls during recording to log them."""
    global _recording, _current_recording
    with _recording_lock:
        if _recording and name not in ("start_recording_macro", "stop_recording_macro",
                                       "replay_macro", "list_macros", "delete_macro"):
            _current_recording.append({
                "tool": name,
                "arguments": arguments,
                "timestamp": datetime.now().isoformat()
            })

    # Call the original execute
    if _original_execute:
        return _original_execute(name, arguments)
    return {"error": "Original execute not available"}


# ─── Tools ───────────────────────────────────────────────────────

@tool(
    name="start_recording_macro",
    description="Starts recording a macro. All subsequent tool calls will be recorded until stop_recording_macro is called.",
    parameters={
        "type": "object",
        "properties": {
            "macro_name": {
                "type": "string",
                "description": "Name for this macro (e.g., 'morning_routine', 'deploy_project')."
            }
        },
        "required": ["macro_name"]
    }
)
def start_recording_macro(macro_name: str) -> str:
    global _recording, _current_recording, _current_macro_name
    with _recording_lock:
        if _recording:
            return f"Already recording macro '{_current_macro_name}'. Stop it first."
        _recording = True
        _current_recording = []
        _current_macro_name = macro_name
    return f"Recording macro '{macro_name}'. All tool calls will be captured. Say 'stop recording' when done."


@tool(
    name="stop_recording_macro",
    description="Stops recording the current macro and saves it.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
def stop_recording_macro() -> str:
    global _recording, _current_recording, _current_macro_name
    with _recording_lock:
        if not _recording:
            return "No macro is currently being recorded."
        _recording = False
        name = _current_macro_name
        steps = list(_current_recording)
        _current_recording = []
        _current_macro_name = ""

    if not steps:
        return f"Macro '{name}' had no steps recorded. Nothing saved."

    _save_macro(name, steps)
    return f"Macro '{name}' saved with {len(steps)} step(s)."


@tool(
    name="replay_macro",
    description="Replays a previously recorded macro by name, executing all its steps in sequence.",
    parameters={
        "type": "object",
        "properties": {
            "macro_name": {
                "type": "string",
                "description": "Name of the macro to replay."
            }
        },
        "required": ["macro_name"]
    }
)
def replay_macro(macro_name: str) -> str:
    macro = _load_macro(macro_name)
    if macro is None:
        return f"Macro '{macro_name}' not found."

    steps = macro.get("steps", [])
    if not steps:
        return f"Macro '{macro_name}' has no steps."

    results = []
    for i, step in enumerate(steps, 1):
        tool_name = step["tool"]
        args = step["arguments"]

        if tool_name in _TOOL_REGISTRY:
            try:
                func = _TOOL_REGISTRY[tool_name]["func"]
                result = func(**args)
                results.append(f"Step {i} ({tool_name}): {str(result)[:100]}")
            except Exception as e:
                results.append(f"Step {i} ({tool_name}): Error - {e}")
        else:
            results.append(f"Step {i} ({tool_name}): Tool not found, skipped")

        time.sleep(0.5)  # Brief delay between steps

    return f"Replayed macro '{macro_name}' ({len(steps)} steps):\n" + "\n".join(results)


@tool(
    name="list_macros",
    description="Lists all saved macros.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
def list_macros() -> str:
    try:
        files = [f for f in os.listdir(MACROS_DIR) if f.endswith(".json")]
        if not files:
            return "No macros saved yet."

        lines = []
        for f in sorted(files):
            path = os.path.join(MACROS_DIR, f)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    macro = json.load(fh)
                name = macro.get("name", f[:-5])
                count = macro.get("step_count", "?")
                created = macro.get("created_at", "unknown")[:10]
                lines.append(f"  • {name} ({count} steps, created {created})")
            except Exception:
                lines.append(f"  • {f[:-5]} (corrupted)")

        return f"Saved macros ({len(files)}):\n" + "\n".join(lines)
    except Exception as e:
        return f"Failed to list macros: {e}"


@tool(
    name="delete_macro",
    description="Deletes a saved macro by name.",
    parameters={
        "type": "object",
        "properties": {
            "macro_name": {
                "type": "string",
                "description": "Name of the macro to delete."
            }
        },
        "required": ["macro_name"]
    }
)
def delete_macro(macro_name: str) -> str:
    path = _get_macro_path(macro_name)
    if not os.path.exists(path):
        return f"Macro '{macro_name}' not found."
    try:
        os.remove(path)
        return f"Macro '{macro_name}' deleted."
    except Exception as e:
        return f"Failed to delete macro: {e}"
