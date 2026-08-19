"""
J.A.R.V.I.S. Claude Builder
═══════════════════════════
Uses the locally-installed **Claude Code CLI** as Jarvis's "build / create
anything" brain — powered by the user's Claude subscription over OAuth, so it
needs NO Anthropic API key and burns NO API credits.

Why this exists:
  The Anthropic *API* (core/llm_provider._anthropic_chat) needs a paid API key
  with credits. The Claude Code *CLI*, however, authenticates with the user's
  Claude.ai Pro/Max subscription. We shell out to it headlessly to get
  best-in-class multi-file building without any billing surprises.

Safety:
  We run with `--permission-mode acceptEdits`, which auto-accepts file writes
  but STILL requires interactive approval for Bash/shell. In headless (`-p`)
  mode there is no one to approve, so shell commands are effectively blocked.
  A misheard voice command therefore cannot run arbitrary commands on the
  system — it can only create files inside the isolated project folder.
"""

import os
import shutil
import subprocess
import logging
import webbrowser

from core.tool_manager import tool

logger = logging.getLogger("jarvis.claude_builder")

# Where Claude-built projects live: ~/.jarvis/projects/<name>/
_PROJECTS_ROOT = os.path.join(os.path.expanduser("~"), ".jarvis", "projects")

# How long to let a single build run before giving up (seconds).
_BUILD_TIMEOUT = 600

# File-only toolset: Claude can read/write/search files but not run shell.
_ALLOWED_TOOLS = "Write Edit Read Glob Grep MultiEdit NotebookEdit"


def _safe_name(name: str) -> str:
    import re
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", (name or "project").strip().lower()).strip("-")
    return slug or "project"


def _find_claude() -> str | None:
    """Locate the Claude Code CLI executable on this machine."""
    for cand in ("claude", "claude.cmd", "claude.exe"):
        path = shutil.which(cand)
        if path:
            return path
    # Common npm global install location on Windows.
    guess = os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd")
    return guess if os.path.exists(guess) else None


def is_available() -> bool:
    """True if the Claude Code CLI is installed (so Jarvis can build via Claude)."""
    return _find_claude() is not None


def _list_files(root: str) -> list[str]:
    out = []
    for base, _, files in os.walk(root):
        for f in files:
            rel = os.path.relpath(os.path.join(base, f), root)
            out.append(rel.replace("\\", "/"))
    return sorted(out)


@tool(
    name="build_with_claude",
    description=(
        "Build or create ANYTHING using Claude (the most capable coding brain), "
        "powered by the user's Claude subscription — no API key needed. Use this "
        "for real, multi-file projects and anything non-trivial: web apps, "
        "websites, Python scripts/tools, games, automations, data scripts, "
        "documents, or refactors. Claude writes actual working files into an "
        "isolated project folder and you get a verified summary of what was "
        "created. PREFER this over 'build_web_app' whenever the request is more "
        "than a single tiny HTML file, or when the user says 'build', 'create', "
        "'make me', 'develop', or 'code'. Provide a clear, detailed 'request'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "description": (
                    "A detailed description of what to build, in plain English. "
                    "Include features, style, and any specifics the user asked for."
                ),
            },
            "project_name": {
                "type": "string",
                "description": "Short name for the project folder, e.g. 'expense-tracker'.",
            },
        },
        "required": ["request", "project_name"],
    },
)
def build_with_claude(request: str, project_name: str) -> str:
    """Drive the Claude Code CLI headlessly to build a project, then verify + report."""
    claude = _find_claude()
    if not claude:
        return (
            "Claude Code CLI is not installed, so I can't use Claude as the build "
            "brain. Install it with: npm install -g @anthropic-ai/claude-code, then "
            "run 'claude' once to sign in. (I can still build simple single-file "
            "apps with build_web_app in the meantime.)"
        )

    if not request or not request.strip():
        return "Error: 'request' is empty — tell me what to build."

    proj_dir = os.path.join(_PROJECTS_ROOT, _safe_name(project_name))
    os.makedirs(proj_dir, exist_ok=True)

    before = set(_list_files(proj_dir))

    prompt = (
        "You are the build engine for a voice assistant. Build the following, "
        "creating real, complete, working files in the CURRENT directory. Do not "
        "ask questions — make sensible choices and finish. If it is a web app, "
        "make it a self-contained set of files that runs by opening index.html "
        "(no build step or dev server required unless truly necessary). When "
        "done, briefly list the files you created and how to run it.\n\n"
        f"BUILD REQUEST:\n{request.strip()}\n"
    )

    cmd = [
        claude,
        "-p",
        "--output-format", "text",
        "--permission-mode", "acceptEdits",
        "--allowedTools", _ALLOWED_TOOLS,
        "--add-dir", proj_dir,
    ]

    logger.info("[ClaudeBuilder] Building '%s' in %s", project_name, proj_dir)
    try:
        completed = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            cwd=proj_dir,
            timeout=_BUILD_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        created = sorted(set(_list_files(proj_dir)) - before)
        made = ("\nFiles created so far:\n" + "\n".join(f"  • {f}" for f in created)) if created else ""
        return (
            f"The build ran long and I stopped it after {_BUILD_TIMEOUT // 60} minutes. "
            f"Some work may be saved in {proj_dir}.{made}"
        )
    except Exception as e:
        logger.error("[ClaudeBuilder] Failed to run Claude CLI: %s", e)
        return f"Error launching the Claude build engine: {e}"

    after = set(_list_files(proj_dir))
    created = sorted(after - before)
    summary = (completed.stdout or "").strip()

    # Honest verification: did Claude actually produce files?
    if not created:
        detail = summary or (completed.stderr or "").strip() or "no output"
        return (
            f"Claude ran but no new files appeared in {proj_dir}. It said:\n{detail[:800]}"
        )

    # If there's a runnable entry point, open it.
    opened_note = ""
    index_html = os.path.join(proj_dir, "index.html")
    if os.path.exists(index_html):
        try:
            webbrowser.open("file:///" + index_html.replace("\\", "/"))
            opened_note = " I opened it in your browser."
        except Exception:
            pass

    file_lines = "\n".join(f"  • {f}" for f in created[:25])
    more = f"\n  … and {len(created) - 25} more" if len(created) > 25 else ""
    tail = ("\n\nClaude's notes:\n" + summary[-600:]) if summary else ""
    return (
        f"Built '{project_name}' with Claude — {len(created)} file(s) created in "
        f"{proj_dir}.{opened_note}\n{file_lines}{more}{tail}"
    )


@tool(
    name="list_claude_projects",
    description="List projects previously built with Claude via build_with_claude.",
    parameters={"type": "object", "properties": {}},
)
def list_claude_projects() -> str:
    if not os.path.isdir(_PROJECTS_ROOT):
        return "No Claude-built projects yet."
    projs = [d for d in os.listdir(_PROJECTS_ROOT)
             if os.path.isdir(os.path.join(_PROJECTS_ROOT, d))]
    if not projs:
        return "No Claude-built projects yet."
    lines = []
    for p in sorted(projs):
        n = len(_list_files(os.path.join(_PROJECTS_ROOT, p)))
        lines.append(f"• {p} ({n} files)")
    return "Claude-built projects:\n" + "\n".join(lines)
