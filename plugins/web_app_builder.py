"""
J.A.R.V.I.S. Simple Web App Builder
Builds self-contained web apps as a single HTML file (inline CSS + JS) and
opens them in the browser. No npm, no bundler, no dev server — it just works.

This is the reliable path for "build me a calculator / to-do list / dashboard"
style requests, replacing the heavy Bolt/Lovable scaffold+dev-server pipeline.
"""

import os
import re
import time
import logging
import webbrowser

from core.tool_manager import tool

logger = logging.getLogger("jarvis.web_app_builder")

# Where built apps live: ~/.jarvis/apps/<name>/index.html
_APPS_ROOT = os.path.join(os.path.expanduser("~"), ".jarvis", "apps")


def _safe_name(name: str) -> str:
    """Turn an app title into a safe folder name."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", (name or "app").strip().lower()).strip("-")
    return slug or "app"


@tool(
    name="build_web_app",
    description=(
        "Build a simple, self-contained web app or tool from a SINGLE HTML "
        "document with inline CSS and JavaScript (no npm, no build step, no dev "
        "server). Writes index.html and opens it in the browser. Use this for "
        "calculators, to-do lists, timers, dashboards, games, landing pages — "
        "anything that runs in one HTML file. ALWAYS prefer this over any "
        "bolt/lovable/scaffold/dev-server tool for building web apps. The 'html' "
        "argument must be the COMPLETE HTML document starting with <!DOCTYPE html>."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Short name/title of the app, e.g. 'calculator'.",
            },
            "html": {
                "type": "string",
                "description": "The full, self-contained HTML document (inline CSS/JS).",
            },
        },
        "required": ["name", "html"],
    },
)
def build_web_app(name: str, html: str) -> str:
    """Write a single-file web app and open it in the default browser."""
    if not html or "<" not in html:
        return "Error: 'html' must be a complete HTML document (got empty/invalid content)."

    app_dir = os.path.join(_APPS_ROOT, _safe_name(name))
    os.makedirs(app_dir, exist_ok=True)
    index_path = os.path.join(app_dir, "index.html")

    try:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        logger.error("[WebAppBuilder] Failed to write %s: %s", index_path, e)
        return f"Error writing the app file: {e}"

    # Verify the file exists and is non-trivial before claiming success.
    if not os.path.exists(index_path) or os.path.getsize(index_path) < 30:
        return f"Error: the app file was not written correctly at {index_path}."

    # Open it in the default browser via a file:// URL (works with no server).
    opened = False
    try:
        url = "file:///" + index_path.replace("\\", "/")
        opened = webbrowser.open(url)
    except Exception as e:
        logger.warning("[WebAppBuilder] Could not auto-open browser: %s", e)

    size_kb = os.path.getsize(index_path) / 1024.0
    status = "opened it in your browser" if opened else "saved it (open it manually)"
    return (
        f"Built '{name}' as a self-contained web app ({size_kb:.1f} KB) and {status}.\n"
        f"File: {index_path}"
    )


@tool(
    name="list_web_apps",
    description="List the simple web apps previously built with build_web_app.",
    parameters={"type": "object", "properties": {}},
)
def list_web_apps() -> str:
    if not os.path.isdir(_APPS_ROOT):
        return "No web apps built yet."
    apps = [d for d in os.listdir(_APPS_ROOT)
            if os.path.exists(os.path.join(_APPS_ROOT, d, "index.html"))]
    if not apps:
        return "No web apps built yet."
    return "Built web apps:\n" + "\n".join(f"• {a}" for a in sorted(apps))
