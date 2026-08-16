"""
J.A.R.V.I.S. Control Plane
═══════════════════════════
Runtime safety controls, kept deliberately separate from the stateless helpers
in ``security.py``:

  * Emergency Stop — a process-wide flag that halts in-flight autonomous work
    (the agentic loop checks it between every step).
  * Audit Log — an append-only JSONL record of every tool execution, with
    secret-looking arguments redacted, for real observability.

Both are exposed through a single process-wide singleton.
"""

import os
import json
import time
import threading
import logging
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger("jarvis.control")

# Argument keys whose values must never be written to the audit log.
_SECRET_KEY_HINTS = (
    "key", "token", "secret", "password", "passwd", "pwd",
    "api_key", "apikey", "authorization", "auth", "credential", "cookie",
)


def _redact(obj: Any) -> Any:
    """Recursively redact secret-looking values and truncate long strings."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if any(hint in str(k).lower() for hint in _SECRET_KEY_HINTS):
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [_redact(v) for v in obj]
    if isinstance(obj, str) and len(obj) > 400:
        return obj[:400] + "…"
    return obj


class ControlPlane:
    """Process-wide emergency stop + tool audit log."""

    def __init__(self):
        self._stop = threading.Event()
        self._stopped_at: float = 0.0
        self._lock = threading.Lock()
        self._audit_path = os.path.join(
            os.path.expanduser("~"), ".jarvis", "logs", "audit.jsonl"
        )
        try:
            os.makedirs(os.path.dirname(self._audit_path), exist_ok=True)
        except Exception as e:
            logger.warning("[Control] Could not create audit dir: %s", e)

    # ── Emergency stop ───────────────────────────────────────────
    def request_stop(self, reason: str = "user") -> None:
        """Signal all autonomous work to halt as soon as it checks the flag."""
        self._stop.set()
        self._stopped_at = time.time()
        logger.warning("[Control] EMERGENCY STOP requested (%s)", reason)
        self.audit("EMERGENCY_STOP", {"reason": reason}, "stop_requested", source="control")

    def clear_stop(self) -> None:
        """Reset the stop flag so new work can run (called when a new task starts)."""
        if self._stop.is_set():
            logger.info("[Control] Emergency stop cleared.")
        self._stop.clear()

    def is_stopped(self) -> bool:
        return self._stop.is_set()

    # ── Audit log ────────────────────────────────────────────────
    def audit(self, tool: str, args: Any, status: Any, source: str = "tool") -> None:
        """Append one tool execution record to the audit log (best-effort)."""
        try:
            record = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "source": source,
                "tool": tool,
                "args": _redact(args if isinstance(args, (dict, list)) else {"value": args}),
                "status": str(status)[:200],
            }
            line = json.dumps(record, default=str)
            with self._lock:
                with open(self._audit_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as e:
            logger.debug("[Control] Audit write failed: %s", e)

    def tail_audit(self, n: int = 20) -> List[Dict[str, Any]]:
        """Return the most recent ``n`` audit records (newest last)."""
        try:
            with open(self._audit_path, encoding="utf-8") as f:
                lines = f.readlines()[-n:]
            return [json.loads(ln) for ln in lines if ln.strip()]
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.debug("[Control] Audit read failed: %s", e)
            return []


_instance: "ControlPlane | None" = None


def get_control_plane() -> ControlPlane:
    global _instance
    if _instance is None:
        _instance = ControlPlane()
    return _instance
