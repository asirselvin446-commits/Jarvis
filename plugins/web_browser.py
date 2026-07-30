"""
J.A.R.V.I.S. Web Browser Plugin
Handles web searches and opening URLs.
"""

import webbrowser
import urllib.parse
import subprocess
from config import APP_PATHS, DEFAULT_BROWSER

def _is_process_running(process_name: str) -> bool:
    """Check if a process is currently running."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        return process_name.lower() in result.stdout.lower()
    except Exception:
        return False


def _open_url(url: str):
    """Opens a URL using the configured default browser, falling back to system default.
    
    Handles the Chrome profile picker issue: when Chrome is already running,
    passing --profile-directory can trigger the profile picker dialog.
    Instead, we detect if Chrome is running and open via 'start' command
    which appends to the existing session.
    """
    if DEFAULT_BROWSER and DEFAULT_BROWSER.lower() in APP_PATHS:
        browser_path = APP_PATHS[DEFAULT_BROWSER.lower()]
        try:
            if "chrome.exe" in browser_path.lower():
                if _is_process_running("chrome.exe"):
                    # Chrome is running — open new tab in existing session
                    subprocess.Popen(f'start chrome "{url}"', shell=True)
                else:
                    # Chrome is NOT running — launch with profile flag
                    subprocess.Popen(f'"{browser_path}" --profile-directory=Default "{url}"', shell=True)
            elif "msedge.exe" in browser_path.lower():
                if _is_process_running("msedge.exe"):
                    subprocess.Popen(f'start msedge "{url}"', shell=True)
                else:
                    subprocess.Popen(f'"{browser_path}" "{url}"', shell=True)
            else:
                subprocess.Popen(f'"{browser_path}" "{url}"', shell=True)
            return
        except Exception as e:
            print(f"[web_browser] Failed to open with {DEFAULT_BROWSER}: {e}")
            
    webbrowser.open(url)
from core.tool_manager import tool

@tool(
    name="search_google",
    description="Searches Google for a specific query.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search term to query on Google."
            }
        },
        "required": ["query"]
    }
)
def search_google(query: str) -> str:
    url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
    _open_url(url)
    return f"Opened Google search for '{query}'."

@tool(
    name="play_youtube",
    description="Plays a specific song, music, or video directly on YouTube (opens and starts playing automatically).",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The name of the song, music, or video to play."
            }
        },
        "required": ["query"]
    }
)
def play_youtube(query: str) -> str:
    import urllib.request
    import re
    
    clean_query = query.lower().replace("open youtube and play", "").replace("play", "").replace("on youtube", "").strip()
    encoded = urllib.parse.quote_plus(clean_query if clean_query else query)
    search_url = f"https://www.youtube.com/results?search_query={encoded}"
    
    try:
        req = urllib.request.Request(
            search_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
        video_ids = re.findall(r"watch\?v=(\S{11})", html)
        if video_ids:
            play_url = f"https://www.youtube.com/watch?v={video_ids[0]}"
            _open_url(play_url)
            return f"Playing '{clean_query if clean_query else query}' on YouTube."
    except Exception as e:
        print(f"[play_youtube] Direct fetch error: {e}")
        
    _open_url(search_url)
    return f"Opened YouTube search for '{query}'."

@tool(
    name="search_youtube",
    description="Searches YouTube for a video or plays it directly.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The video or topic to search for or play on YouTube."
            }
        },
        "required": ["query"]
    }
)
def search_youtube(query: str) -> str:
    return play_youtube(query)

@tool(
    name="open_website",
    description="Opens a specific website URL in the default browser.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL of the website to open (e.g., 'github.com', 'https://reddit.com')."
            }
        },
        "required": ["url"]
    }
)
def open_website(url: str) -> str:
    if not url.startswith("http"):
        url = "https://" + url
    _open_url(url)
    return f"Opened website: {url}."
