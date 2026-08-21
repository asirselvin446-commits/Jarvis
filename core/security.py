"""
J.A.R.V.I.S. Security Module
Centralized security utilities for input validation, path sandboxing,
command safety checking, and rate limiting.
"""

import os
import re
import time
import threading
from typing import Optional
from urllib.parse import urlparse


# ─── Path Sandboxing ─────────────────────────────────────────────

# Directories that should NEVER be written to by Jarvis tools
BLOCKED_WRITE_DIRS = [
    os.path.normpath(r"C:\Windows"),
    os.path.normpath(r"C:\Program Files"),
    os.path.normpath(r"C:\Program Files (x86)"),
    os.path.normpath(r"C:\ProgramData"),
    os.path.normpath(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")),
    os.path.normpath(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "SysWOW64")),
]

# Files that should never be read (sensitive system files)
BLOCKED_READ_PATTERNS = [
    r"SAM$", r"SYSTEM$", r"SECURITY$", r"SOFTWARE$",  # Registry hives
    r"\.pem$", r"\.key$", r"id_rsa", r"id_ed25519",    # Private keys
    r"ntds\.dit$",                                       # Active Directory DB
]


def sanitize_path(path: str, allow_write: bool = False) -> str:
    """
    Validate and normalize a file path for safety.
    
    Args:
        path: The file path to validate.
        allow_write: If True, also check against write-blocked directories.
    
    Returns:
        The normalized absolute path if safe.
    
    Raises:
        PermissionError: If the path is blocked for security reasons.
    """
    # Expand user home directory
    expanded = os.path.expanduser(path)
    # Resolve to absolute, canonical path (resolves .., symlinks, etc.)
    resolved = os.path.normpath(os.path.abspath(expanded))

    # Block path traversal attempts
    if ".." in path:
        raise PermissionError(f"Path traversal blocked: '{path}'")

    # Check against blocked read patterns
    for pattern in BLOCKED_READ_PATTERNS:
        if re.search(pattern, resolved, re.IGNORECASE):
            raise PermissionError(f"Access to sensitive file blocked: '{path}'")

    # Check write-blocked directories
    if allow_write:
        for blocked_dir in BLOCKED_WRITE_DIRS:
            if resolved.lower().startswith(blocked_dir.lower()):
                raise PermissionError(
                    f"Writing to system directory blocked: '{path}' "
                    f"(protected: {blocked_dir})"
                )

    return resolved


# ─── URL Validation ──────────────────────────────────────────────

ALLOWED_URL_SCHEMES = {"http", "https"}
BLOCKED_URL_SCHEMES = {"file", "javascript", "data", "vbscript", "ftp"}


def sanitize_url(url: str) -> str:
    """
    Validate a URL for safety.
    
    Args:
        url: The URL to validate.
    
    Returns:
        The validated URL (with https:// prepended if no scheme).
    
    Raises:
        ValueError: If the URL uses a blocked scheme.
    """
    url = url.strip()

    # Prepend https:// if no scheme
    if not url.startswith(("http://", "https://")):
        # Check for blocked schemes before adding https
        for scheme in BLOCKED_URL_SCHEMES:
            if url.lower().startswith(f"{scheme}:"):
                raise ValueError(f"Blocked URL scheme: '{scheme}' in '{url}'")
        url = "https://" + url

    parsed = urlparse(url)

    if parsed.scheme.lower() in BLOCKED_URL_SCHEMES:
        raise ValueError(f"Blocked URL scheme: '{parsed.scheme}' in '{url}'")

    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
        raise ValueError(f"Unsupported URL scheme: '{parsed.scheme}' in '{url}'")

    if not parsed.netloc:
        raise ValueError(f"Invalid URL (no host): '{url}'")

    return url


# ─── Command Safety ─────────────────────────────────────────────

DANGEROUS_COMMAND_PATTERNS = [
    # Disk/partition destruction
    r"rm\s+-rf\s+/",
    r"rmdir\s+/s\s+/q\s+c:\\",
    r"format\s+[a-z]:",
    r"del\s+/[sfq]+\s+c:\\",
    r"rd\s+/s\s+/q\s+c:\\",
    r"cipher\s+/w:",
    r"diskpart",

    # System file destruction
    r"Remove-Item.*-Recurse.*C:\\Windows",
    r"Remove-Item.*-Recurse.*C:\\Program",
    r"del\s+/f\s+/s\s+c:\\windows",
    r"del\s+/f\s+/s\s+c:\\program",

    # System commands that should go through dedicated skills
    r"Stop-Computer",
    r"Restart-Computer",
    r"shutdown\s+/[srfta]",

    # Registry manipulation
    r"reg\s+delete.*HKL[CM]",
    r"reg\s+delete.*HKCR",
    r"reg\s+add.*HKLM",

    # Boot/system config
    r"bcdedit",
    r"sfc\s+/",
    r"takeown\s+/f\s+c:\\windows",
    r"icacls\s+c:\\windows",

    # User/group manipulation
    r"net\s+user\s+",
    r"net\s+localgroup\s+",
    r"wmic\s+useraccount",

    # Process killing (system processes)
    r"taskkill\s+/f\s+/im\s+(csrss|lsass|winlogon|svchost|smss)",

    # Encoded/obfuscated execution (common malware technique)
    r"powershell.*-[Ee]nc\w*\s+",
    r"powershell.*-[Ee]ncodedCommand",

    # Download-and-execute patterns
    r"Invoke-WebRequest.*\|\s*iex",
    r"Invoke-Expression.*Invoke-WebRequest",
    r"curl.*\|\s*(bash|sh|powershell|cmd)",
    r"wget.*\|\s*(bash|sh|powershell|cmd)",
    r"iex\s*\(.*Net\.WebClient",
    
    # Recursive delete from dangerous locations
    r"Remove-Item\s+-Path\s+['\"]?C:\\",
]


def is_safe_command(command: str) -> bool:
    """
    Check if a shell command is safe to execute.
    
    Args:
        command: The command string to check.
    
    Returns:
        True if the command appears safe, False if it matches a dangerous pattern.
    """
    for pattern in DANGEROUS_COMMAND_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False
    return True


def get_blocked_reason(command: str) -> Optional[str]:
    """Return the specific reason a command was blocked, or None if safe."""
    for pattern in DANGEROUS_COMMAND_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return f"Matched dangerous pattern: {pattern}"
    return None


# ─── Tool Safety ─────────────────────────────────────────────────

# Substrings in a tool name that mark it as potentially destructive,
# irreversible, or outward-facing. Acts as a safety net for tools that were
# never given an explicit ``is_dangerous`` flag by the @tool decorator.
DANGEROUS_TOOL_NAME_HINTS = (
    "delete", "remove", "kill", "uninstall", "format", "wipe", "erase",
    "shutdown", "reboot", "restart", "send", "email", "message", "whatsapp",
    "post", "publish", "buy", "purchase", "pay", "transfer", "commit", "push",
    "terminal", "powershell", "shell", "exec", "run_python", "write_code",
)


def is_dangerous_tool(tool_name: str, meta: Optional[dict] = None) -> bool:
    """Decide whether a tool needs explicit user confirmation before running.

    Single source of truth for both execution paths (the single-shot
    Orchestrator pipeline and the agentic ReAct loop), so a tool can never be
    gated on one path and slip through unchecked on the other.

    Combines the declared safety flags from the @tool decorator with a
    name-based heuristic, since most destructive tools were never flagged.

    Args:
        tool_name: The registered name of the tool.
        meta: The tool's spec dict (or any mapping exposing ``is_dangerous`` /
            ``requires_confirmation``). Optional -- when omitted, only the
            name heuristic applies.

    Returns:
        True if the tool should require confirmation.
    """
    if meta and (meta.get("is_dangerous") or meta.get("requires_confirmation")):
        return True
    low = (tool_name or "").lower()
    return any(hint in low for hint in DANGEROUS_TOOL_NAME_HINTS)


# ─── Rate Limiter ────────────────────────────────────────────────

class RateLimiter:
    """
    Simple token bucket rate limiter.
    Thread-safe.
    
    Usage:
        limiter = RateLimiter(max_requests=30, window_seconds=60)
        if limiter.allow():
            # Process request
        else:
            # Reject (429 Too Many Requests)
    """

    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._tokens = max_requests
        self._last_refill = time.time()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        """Check if a request should be allowed. Returns True if allowed."""
        with self._lock:
            now = time.time()
            # Refill tokens based on elapsed time
            elapsed = now - self._last_refill
            refill = elapsed * (self.max_requests / self.window_seconds)
            self._tokens = min(self.max_requests, self._tokens + refill)
            self._last_refill = now

            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False

    def reset(self):
        """Reset the rate limiter to full capacity."""
        with self._lock:
            self._tokens = self.max_requests
            self._last_refill = time.time()
