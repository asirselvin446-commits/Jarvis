"""
J.A.R.V.I.S. File Operations Plugin
Find, open, move, copy, rename and delete files by voice.

plugins/file_manager.py only covered opening and creating *folders*, which
left the most common everyday PC-control requests impossible ("where's my
resume?", "open that PDF", "move these to Documents", "delete that file").

Safety:
  * Deletes go to the **Recycle Bin**, never a permanent unlink, so a
    misheard command is always recoverable. Implemented with the Windows
    Shell API (SHFileOperationW) so it needs no extra dependency.
  * Protected system locations (Windows, Program Files, drive roots) are
    refused outright.
  * Destructive tools are marked is_dangerous so the agentic loop's safety
    gate requires explicit confirmation under the default 'guarded' autonomy.
"""

import os
import shutil
import fnmatch
import logging
import ctypes
from ctypes import wintypes

from core.tool_manager import tool
from config import DIRECTORIES, USER_HOME

logger = logging.getLogger("jarvis.file_operations")

# Folders searched when the user doesn't name a location.
_DEFAULT_SEARCH_DIRS = ["desktop", "downloads", "documents", "pictures", "videos", "music"]

# Directories never descended into during a search (noise / huge / not user data).
_SKIP_DIR_NAMES = {
    "node_modules", "__pycache__", ".git", ".venv", "venv", "env",
    "AppData", "Application Data", "$RECYCLE.BIN", "System Volume Information",
    ".cache", "site-packages", "dist-info",
}

# Never modify or delete anything inside these.
_PROTECTED_ROOTS = [
    os.environ.get("SystemRoot", r"C:\Windows"),
    os.environ.get("ProgramFiles", r"C:\Program Files"),
    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    os.environ.get("ProgramData", r"C:\ProgramData"),
]

_MAX_SEARCH_RESULTS = 25


# ─── Path helpers ────────────────────────────────────────────────

def _is_protected(path: str) -> bool:
    """True if the path is a system location or a drive root."""
    try:
        real = os.path.abspath(path)
    except Exception:
        return True

    # Drive roots like C:\ — refuse operating on an entire drive.
    if os.path.dirname(real) == real:
        return True

    real_lower = real.lower()
    for root in _PROTECTED_ROOTS:
        if root and real_lower.startswith(os.path.abspath(root).lower()):
            return True
    return False


def _resolve_location(location: str) -> str | None:
    """Turn a friendly folder name ('downloads') or a path into a real directory."""
    if not location:
        return None
    key = location.strip().lower()
    if key in DIRECTORIES:
        return DIRECTORIES[key]
    aliases = {
        "home": USER_HOME, "user": USER_HOME, "profile": USER_HOME,
        "docs": DIRECTORIES.get("documents"), "pics": DIRECTORIES.get("pictures"),
        "photos": DIRECTORIES.get("pictures"), "vids": DIRECTORIES.get("videos"),
        "movies": DIRECTORIES.get("videos"),
    }
    if key in aliases and aliases[key]:
        return aliases[key]
    expanded = os.path.expanduser(os.path.expandvars(location))
    return expanded if os.path.isdir(expanded) else None


def _search(pattern: str, roots: list[str], limit: int) -> list[str]:
    """Walk roots looking for filenames matching a glob pattern."""
    matches: list[str] = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIR_NAMES and not d.startswith(".")]
            for name in files:
                if fnmatch.fnmatch(name.lower(), pattern):
                    matches.append(os.path.join(base, name))
                    if len(matches) >= limit:
                        return matches
    return matches


def _resolve_file(name_or_path: str) -> tuple[str | None, str | None]:
    """Resolve a file reference to a real path.

    Returns (path, error). Accepts a full path, or a bare filename which is
    searched for across the user's common folders.
    """
    if not name_or_path or not name_or_path.strip():
        return None, "No file was specified."

    raw = name_or_path.strip().strip('"')
    expanded = os.path.expanduser(os.path.expandvars(raw))
    if os.path.exists(expanded):
        return os.path.abspath(expanded), None

    # Treat it as a name to search for.
    pattern = raw.lower()
    if not any(ch in pattern for ch in "*?"):
        pattern = f"*{pattern}*"
    roots = [DIRECTORIES.get(d) for d in _DEFAULT_SEARCH_DIRS]
    found = _search(pattern, [r for r in roots if r], limit=5)

    if not found:
        return None, f"I couldn't find any file matching '{raw}'."
    if len(found) > 1:
        listing = "\n".join(f"  • {p}" for p in found)
        return None, (f"'{raw}' matches {len(found)} files — tell me which one:\n{listing}")
    return found[0], None


# ─── Recycle Bin deletion (Windows Shell API) ────────────────────

_FO_DELETE = 0x0003
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040  # this is what routes to the Recycle Bin
_FOF_NOERRORUI = 0x0400


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def _recycle(path: str) -> tuple[bool, str]:
    """Send a file or folder to the Recycle Bin. Returns (ok, message)."""
    # Prefer send2trash when the user has it installed.
    try:
        from send2trash import send2trash
        send2trash(path)
        return True, ""
    except ImportError:
        pass
    except Exception as e:
        return False, str(e)

    try:
        op = _SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = _FO_DELETE
        # pFrom must be double-null-terminated.
        op.pFrom = path + "\0\0"
        op.pTo = None
        op.fFlags = _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT | _FOF_NOERRORUI
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if result != 0:
            return False, f"Windows shell error code {result}"
        if op.fAnyOperationsAborted:
            return False, "the operation was aborted"
        return True, ""
    except Exception as e:
        return False, str(e)


# ─── Tools ───────────────────────────────────────────────────────

@tool(
    name="find_files",
    description=(
        "Search for files by name anywhere in the user's folders. Use this to "
        "answer 'where is my resume', 'find the budget spreadsheet', or to "
        "locate a file before opening/moving it. Returns matching file paths."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Part of the filename to search for, e.g. 'resume' or '*.pdf'.",
            },
            "location": {
                "type": "string",
                "description": (
                    "Optional folder to search in ('downloads', 'desktop', "
                    "'documents', or a full path). Defaults to all common folders."
                ),
            },
        },
        "required": ["query"],
    },
)
def find_files(query: str, location: str = "") -> str:
    if not query or not query.strip():
        return "Error: no search query was given."

    pattern = query.strip().lower()
    if not any(ch in pattern for ch in "*?"):
        pattern = f"*{pattern}*"

    if location:
        root = _resolve_location(location)
        if not root:
            return f"Error: I couldn't find the folder '{location}'."
        roots = [root]
        where = location
    else:
        roots = [DIRECTORIES.get(d) for d in _DEFAULT_SEARCH_DIRS]
        roots = [r for r in roots if r]
        where = "your common folders"

    matches = _search(pattern, roots, _MAX_SEARCH_RESULTS)
    if not matches:
        return f"No files matching '{query}' were found in {where}."

    lines = "\n".join(f"  • {p}" for p in matches)
    more = f"\n(showing the first {_MAX_SEARCH_RESULTS})" if len(matches) >= _MAX_SEARCH_RESULTS else ""
    return f"Found {len(matches)} file(s) matching '{query}':\n{lines}{more}"


@tool(
    name="list_files",
    description=(
        "List the files in a folder, e.g. 'what's in my downloads'. Accepts a "
        "friendly name ('downloads', 'desktop') or a full path."
    ),
    parameters={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "Folder to list, e.g. 'downloads' or a full path.",
            },
        },
        "required": ["location"],
    },
)
def list_files(location: str) -> str:
    root = _resolve_location(location)
    if not root:
        return f"Error: I couldn't find the folder '{location}'."

    try:
        entries = sorted(os.listdir(root))
    except Exception as e:
        return f"Failed to read '{location}': {e}"

    if not entries:
        return f"The {location} folder is empty."

    folders = [e for e in entries if os.path.isdir(os.path.join(root, e))]
    files = [e for e in entries if not os.path.isdir(os.path.join(root, e))]

    parts = [f"{location} contains {len(folders)} folder(s) and {len(files)} file(s):"]
    for f in folders[:20]:
        parts.append(f"  📁 {f}")
    for f in files[:30]:
        try:
            kb = os.path.getsize(os.path.join(root, f)) / 1024.0
            parts.append(f"  📄 {f} ({kb:.0f} KB)")
        except Exception:
            parts.append(f"  📄 {f}")
    if len(entries) > 50:
        parts.append(f"  … and {len(entries) - 50} more")
    return "\n".join(parts)


@tool(
    name="open_file",
    description=(
        "Open a file in its default application (PDF, document, image, video, "
        "spreadsheet, etc). Accepts a full path or just a filename to search for."
    ),
    parameters={
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Filename or full path, e.g. 'resume.pdf'.",
            },
        },
        "required": ["file"],
    },
)
def open_file(file: str) -> str:
    path, err = _resolve_file(file)
    if err:
        return err
    try:
        os.startfile(path)
        return f"Opened {os.path.basename(path)} ({path})."
    except Exception as e:
        return f"Failed to open '{path}': {e}"


@tool(
    name="move_file",
    description=(
        "Move a file to a different folder. Use for 'move that download into "
        "Documents' style requests."
    ),
    parameters={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Filename or full path to move."},
            "destination": {
                "type": "string",
                "description": "Destination folder ('documents', 'desktop', or a full path).",
            },
        },
        "required": ["file", "destination"],
    },
)
def move_file(file: str, destination: str) -> str:
    path, err = _resolve_file(file)
    if err:
        return err
    if _is_protected(path):
        return f"Refused: '{path}' is in a protected system location."

    dest_dir = _resolve_location(destination)
    if not dest_dir:
        return f"Error: destination folder '{destination}' was not found."
    if _is_protected(dest_dir):
        return f"Refused: '{dest_dir}' is a protected system location."

    target = os.path.join(dest_dir, os.path.basename(path))
    if os.path.exists(target):
        return f"A file named '{os.path.basename(path)}' already exists in {destination}. Rename it first."

    try:
        shutil.move(path, target)
    except Exception as e:
        return f"Failed to move the file: {e}"

    if not os.path.exists(target):
        return f"Error: the move reported no error but '{target}' does not exist."
    return f"Moved {os.path.basename(path)} to {destination} ({target})."


@tool(
    name="copy_file",
    description="Copy a file into another folder, leaving the original in place.",
    parameters={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Filename or full path to copy."},
            "destination": {
                "type": "string",
                "description": "Destination folder ('documents', 'desktop', or a full path).",
            },
        },
        "required": ["file", "destination"],
    },
)
def copy_file(file: str, destination: str) -> str:
    path, err = _resolve_file(file)
    if err:
        return err

    dest_dir = _resolve_location(destination)
    if not dest_dir:
        return f"Error: destination folder '{destination}' was not found."
    if _is_protected(dest_dir):
        return f"Refused: '{dest_dir}' is a protected system location."

    target = os.path.join(dest_dir, os.path.basename(path))
    if os.path.exists(target):
        return f"A file named '{os.path.basename(path)}' already exists in {destination}."

    try:
        shutil.copy2(path, target)
    except Exception as e:
        return f"Failed to copy the file: {e}"

    if not os.path.exists(target):
        return f"Error: the copy reported no error but '{target}' does not exist."
    return f"Copied {os.path.basename(path)} to {destination} ({target})."


@tool(
    name="rename_file",
    description="Rename a file, keeping it in the same folder.",
    parameters={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Filename or full path to rename."},
            "new_name": {
                "type": "string",
                "description": "The new filename, including extension.",
            },
        },
        "required": ["file", "new_name"],
    },
)
def rename_file(file: str, new_name: str) -> str:
    path, err = _resolve_file(file)
    if err:
        return err
    if _is_protected(path):
        return f"Refused: '{path}' is in a protected system location."

    clean = os.path.basename(new_name.strip())
    if not clean:
        return "Error: the new name is empty."

    target = os.path.join(os.path.dirname(path), clean)
    if os.path.exists(target):
        return f"A file named '{clean}' already exists in that folder."

    try:
        os.rename(path, target)
    except Exception as e:
        return f"Failed to rename the file: {e}"

    if not os.path.exists(target):
        return f"Error: the rename reported no error but '{target}' does not exist."
    return f"Renamed {os.path.basename(path)} to {clean}."


@tool(
    name="delete_file",
    description=(
        "Delete a file by moving it to the Recycle Bin (recoverable, never a "
        "permanent delete). Requires the user's confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Filename or full path to delete."},
        },
        "required": ["file"],
    },
    requires_confirmation=True,
    is_dangerous=True,
)
def delete_file(file: str) -> str:
    path, err = _resolve_file(file)
    if err:
        return err
    if _is_protected(path):
        return f"Refused: '{path}' is in a protected system location."

    ok, msg = _recycle(path)
    if not ok:
        return f"Failed to delete '{path}': {msg}"
    if os.path.exists(path):
        return f"Error: '{path}' still exists after the delete."
    return f"Moved {os.path.basename(path)} to the Recycle Bin. It can be restored from there."
