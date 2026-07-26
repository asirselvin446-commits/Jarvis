"""
J.A.R.V.I.S. Vision Agent
Uses Qwen2.5-VL 3B via Ollama to understand the screen.
"""

import os
import base64
import requests
from io import BytesIO
import pyautogui
from PIL import Image
from core.tool_manager import tool

OLLAMA_VISION_URL = "http://localhost:11434/api/generate"
VISION_MODEL = "qwen2.5vl:3b"

class VisionAgent:
    def __init__(self):
        pass

    def _capture_screen_base64(self) -> str:
        """Capture the screen and return it as a base64 encoded string."""
        img = pyautogui.screenshot()
        # Resize to save bandwidth/VRAM if needed, or convert to RGB
        img = img.convert("RGB")
        img.thumbnail((1280, 720)) # Reduce resolution for faster processing
        
        buffered = BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def analyze_screen(self, prompt: str) -> str:
        """Send a screenshot and a prompt to the Vision model."""
        b64_image = self._capture_screen_base64()
        
        payload = {
            "model": VISION_MODEL,
            "prompt": prompt,
            "images": [b64_image],
            "stream": False,
            "options": {
                "temperature": 0.1
            }
        }
        
        try:
            resp = requests.post(OLLAMA_VISION_URL, json=payload, timeout=120)
            if resp.status_code == 200:
                return resp.json().get("response", "")
            return f"Vision Model Error: {resp.status_code} {resp.text}"
        except Exception as e:
            return f"Failed to connect to Vision Model: {e}"

# Expose Vision capabilities as tools for the Brain to use

_vision_agent = VisionAgent()

@tool(
    name="read_screen_text",
    description="Captures the screen and extracts text, reading what is currently visible on the monitor.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
def read_screen_text() -> str:
    return _vision_agent.analyze_screen("Extract all readable text from this screen.")

@tool(
    name="describe_screen",
    description="Captures the screen and provides a detailed description of what is visible (e.g., UI elements, open apps).",
    parameters={
        "type": "object",
        "properties": {}
    }
)
def describe_screen() -> str:
    return _vision_agent.analyze_screen("Describe what is on this screen in detail. What applications are open? Are there any errors?")

@tool(
    name="find_ui_element",
    description="Captures the screen and searches for a specific UI element, returning its coordinates if found.",
    parameters={
        "type": "object",
        "properties": {
            "element_description": {
                "type": "string",
                "description": "What UI element to look for (e.g., 'blue submit button', 'search bar')."
            }
        },
        "required": ["element_description"]
    }
)
def find_ui_element(element_description: str) -> str:
    prompt = f"Find the '{element_description}' on the screen. Return a JSON object with its approximate x and y coordinates (0-100% relative to screen dimensions)."
    return _vision_agent.analyze_screen(prompt)
