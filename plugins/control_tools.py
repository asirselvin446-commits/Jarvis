"""
J.A.R.V.I.S. Control Tools
Expose the runtime safety control plane (emergency stop + audit log) as tools
the agent and user can invoke.
"""

from core.tool_manager import tool
from core.control import get_control_plane


@tool(
    name="emergency_stop",
    description=(
        "Immediately halt all running autonomous tasks and automation. Use when "
        "the user says stop, cancel, abort, or halt. Safe to call anytime."
    ),
    parameters={"type": "object", "properties": {}},
)
def emergency_stop() -> str:
    get_control_plane().request_stop("emergency_stop tool")
    return "Emergency stop engaged. All active autonomous tasks are being halted."


@tool(
    name="resume_after_stop",
    description=(
        "Clear a previously engaged emergency stop so new autonomous tasks can "
        "run again. Only use after the user asks to resume or continue."
    ),
    parameters={"type": "object", "properties": {}},
)
def resume_after_stop() -> str:
    get_control_plane().clear_stop()
    return "Emergency stop cleared. Ready to run tasks again."


@tool(
    name="get_recent_actions",
    description=(
        "Return a summary of the most recent tool executions from the audit log "
        "(what Jarvis actually did). Useful for 'what did you just do?' or review."
    ),
    parameters={
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": "How many recent actions to return (default 10).",
            }
        },
    },
)
def get_recent_actions(count: int = 10) -> str:
    records = get_control_plane().tail_audit(max(1, min(int(count or 10), 50)))
    if not records:
        return "No recorded actions yet."
    lines = []
    for r in records:
        ts = r.get("ts", "")[-8:]  # HH:MM:SS
        lines.append(f"[{ts}] {r.get('tool')} -> {r.get('status')}")
    return "Recent actions:\n" + "\n".join(lines)
