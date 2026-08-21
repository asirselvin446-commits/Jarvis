"""
J.A.R.V.I.S. Secret Redaction
═════════════════════════════
Adapter over the vendored Hermes redactor (core/vendor/hermes/redact.py, MIT).

Jarvis's original redaction matched on *key names* only — `{"api_key": ...}`
became `***REDACTED***`, but a key pasted into a shell command, a bearer token
in a URL, or a password in a connection string went to the audit log in the
clear. Those are exactly the shapes Jarvis produces, because it runs terminal
commands and logs their output.

The Hermes redactor matches on *value* patterns as well, so:

    curl -H "Authorization: Bearer sk-ant-api03-..." → Bearer ***
    postgres://admin:hunter2@db/prod                 → postgres://admin:***@db/prod

Set JARVIS_REDACT_SECRETS=false to disable (not recommended; it only affects
logging and the audit trail, never what tools actually receive).
"""

import os
import logging
from typing import Any

from core.vendor.hermes.redact import (  # noqa: F401  (re-exported)
    RedactingFormatter,
    redact_sensitive_text,
    redact_terminal_output,
)

logger = logging.getLogger("jarvis.redaction")

# Key names whose values are secret regardless of how they look.
_SECRET_KEY_HINTS = (
    "key", "token", "secret", "password", "passwd", "pwd", "auth",
    "credential", "cookie", "session", "bearer", "signature", "private",
)

_MAX_STR = 400


def enabled() -> bool:
    return os.getenv("JARVIS_REDACT_SECRETS", "true").lower() in ("1", "true", "yes", "on")


def redact_text(text: str) -> str:
    """Redact secrets from a free-text string (log line, command, output).

    ``force=True`` so Jarvis's own knob governs this, not the upstream
    HERMES_REDACT_SECRETS variable the vendored module reads at import.
    """
    if not text or not enabled():
        return text
    try:
        return redact_sensitive_text(text, force=True)
    except Exception as e:  # never let redaction break the caller
        logger.debug("[Redaction] Falling back to raw text: %s", e)
        return text


def redact_structure(obj: Any) -> Any:
    """Recursively redact a dict/list of tool arguments.

    Combines both defenses: a secret-looking KEY blanks its whole value (even
    when the value itself looks innocuous), and every surviving string is run
    through the value-level pattern matcher.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if any(hint in str(k).lower() for hint in _SECRET_KEY_HINTS):
                out[k] = "***REDACTED***"
            else:
                out[k] = redact_structure(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact_structure(v) for v in obj]
    if isinstance(obj, str):
        text = redact_text(obj)
        return text[:_MAX_STR] + "…" if len(text) > _MAX_STR else text
    return obj


class JarvisRedactingFormatter(logging.Formatter):
    """Log formatter that redacts secrets, governed by Jarvis's own switch.

    The vendored ``RedactingFormatter`` calls the upstream redactor without
    ``force=True``, so it silently obeys ``HERMES_REDACT_SECRETS`` and ignores
    ``JARVIS_REDACT_SECRETS``. Routing through :func:`redact_text` keeps one
    switch in charge of the whole system.
    """

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def install_log_redaction() -> None:
    """Wrap every root log handler's formatter so secrets never reach a log file.

    Called once at kernel start. Safe to call again — handlers already wrapped
    are skipped.

    This is a backstop, not the primary defense: it only covers handlers that
    exist when it runs, and anything logged before kernel start (scripts,
    tests, import-time failures) never passes through it. Call sites that can
    log a secret should redact at the source as well.
    """
    if not enabled():
        return
    try:
        root = logging.getLogger()
        for handler in root.handlers:
            if isinstance(handler.formatter, (JarvisRedactingFormatter, RedactingFormatter)):
                continue
            existing = handler.formatter
            fmt = getattr(existing, "_fmt", None) or "%(message)s"
            datefmt = getattr(existing, "datefmt", None)
            handler.setFormatter(JarvisRedactingFormatter(fmt, datefmt))
        logger.debug("[Redaction] Log redaction installed on %d handler(s).", len(root.handlers))
    except Exception as e:
        logger.warning("[Redaction] Could not install log redaction: %s", e)
