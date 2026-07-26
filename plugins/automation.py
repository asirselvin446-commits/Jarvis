"""
J.A.R.V.I.S. Automation & System Tools Plugin
Provides command execution, PowerShell scripts, and Clipboard operations.
"""

import subprocess
import os
import sys
from core.tool_manager import tool

@tool(
    name="execute_terminal",
    description="Executes a command in the Windows Command Prompt or shell.",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The command line string to execute."
            }
        },
        "required": ["command"]
    }
)
def execute_terminal(command: str) -> str:
    try:
        res = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=15
        )
        output = res.stdout.strip() or res.stderr.strip() or "Executed successfully."
        return output[:1000]
    except Exception as e:
        return f"Terminal execution failed: {e}"

@tool(
    name="run_powershell",
    description="Executes a PowerShell script or command.",
    parameters={
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "The PowerShell command or script code."
            }
        },
        "required": ["script"]
    }
)
def run_powershell(script: str) -> str:
    try:
        res = subprocess.run(
            ["powershell", "-Command", script],
            capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW
        )
        output = res.stdout.strip() or res.stderr.strip() or "Executed PowerShell script."
        return output[:1000]
    except Exception as e:
        return f"PowerShell execution failed: {e}"

@tool(
    name="clipboard_read",
    description="Reads current text content from the system clipboard.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
def clipboard_read() -> str:
    try:
        import pyautogui
        # PyAutoGUI clipboard read or win32
        res = subprocess.run(
            ["powershell", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return res.stdout.strip() or "Clipboard is empty."
    except Exception as e:
        return f"Could not read clipboard: {e}"

@tool(
    name="clipboard_write",
    description="Writes text content to the system clipboard.",
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to copy to the clipboard."
            }
        },
        "required": ["text"]
    }
)
def clipboard_write(text: str) -> str:
    try:
        safe_text = text.replace("'", "''")
        subprocess.run(
            ["powershell", "-Command", f"Set-Clipboard -Value '{safe_text}'"],
            capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return f"Copied to clipboard: '{text[:50]}...'"
    except Exception as e:
        return f"Could not write to clipboard: {e}"
