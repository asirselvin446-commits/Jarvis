"""
J.A.R.V.I.S. Media Control Plugin
Play/pause/skip media, take screenshots.
"""

import os
import datetime
import pyautogui

from core.tool_manager import tool
from config import SCREENSHOT_DIR

@tool(
    name="media_control",
    description="Controls media playback: play, pause, next_track, previous_track.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["play", "pause", "next_track", "previous_track"],
                "description": "The media action to perform."
            }
        },
        "required": ["action"]
    }
)
def media_control(action: str) -> str:
    try:
        if action == "play" or action == "pause":
            pyautogui.press("playpause")
            return f"Media {action}d."
        elif action == "next_track":
            pyautogui.press("nexttrack")
            return "Skipped to next track."
        elif action == "previous_track":
            pyautogui.press("prevtrack")
            return "Went to previous track."
        else:
            return f"Unknown action: {action}"
    except Exception as e:
        return f"Couldn't control media: {e}"

@tool(
    name="play_spotify",
    description="Searches and plays a song, artist, album, or playlist on Spotify.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The song, artist, or playlist to play on Spotify."
            }
        },
        "required": ["query"]
    }
)
def play_spotify(query: str) -> str:
    import webbrowser
    import urllib.parse
    clean_query = query.lower().replace("play", "").replace("on spotify", "").replace("spotify", "").strip()
    target = clean_query if clean_query else query
    encoded = urllib.parse.quote(target)
    
    try:
        os.startfile(f"spotify:search:{encoded}")
        return f"Searching and playing '{target}' on Spotify app."
    except Exception:
        webbrowser.open(f"https://open.spotify.com/search/{encoded}")
        return f"Opened Spotify Web search for '{target}'."

@tool(
    name="take_screenshot",
    description="Takes a screenshot of the current screen and saves it.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
def take_screenshot() -> str:
    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(SCREENSHOT_DIR, f"screenshot_{timestamp}.png")
        screenshot = pyautogui.screenshot()
        screenshot.save(filepath)
        return f"Screenshot saved to {filepath}."
    except Exception as e:
        return f"Couldn't take screenshot: {e}"
