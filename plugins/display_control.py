"""
J.A.R.V.I.S. Display Control Plugin
Screenshot capture and OCR (read screen text) via voice commands.
"""

import os
import time
from pathlib import Path

from PIL import ImageGrab
import base64
import json
import urllib.request
import io
from core.tool_manager import tool


SCREENSHOT_DIR = Path.home() / "Pictures" / "Jarvis"


@tool(
    name="take_screenshot",
    description="Capture a screenshot of the current screen and save it. Returns the file path.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def take_screenshot() -> str:
    """Capture and save a screenshot."""
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        filepath = SCREENSHOT_DIR / f"screenshot_{int(time.time())}.png"
        img = ImageGrab.grab()
        img.save(str(filepath))
        return f"Screenshot saved to {filepath}"
    except Exception as e:
        return f"Failed to take screenshot: {e}"


@tool(
    name="get_screen_text",
    description=(
        "Read all visible text from the current screen using OCR. "
        "Useful for 'what does the screen say?', 'read the screen', "
        "or extracting information from any application."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def get_screen_text() -> str:
    """OCR the current screen and return extracted text."""
    try:
        from core.ocr_engine import ocr_screen
        text = ocr_screen()
        # ocr_screen reports failure as a message rather than raising.
        if text and text.startswith("OCR failed:"):
            text = ""
        if not text or not text.strip():
            return "No readable text found on the screen."
        # Truncate for voice readback
        if len(text) > 1000:
            return f"Screen text (first 1000 chars):\n{text[:1000]}..."
        return f"Screen text:\n{text}"
    except ImportError:
        # Fallback: try Windows native OCR via PowerShell
        try:
            import subprocess
            img = ImageGrab.grab()
            temp_path = SCREENSHOT_DIR / "_ocr_temp.png"
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            img.save(str(temp_path))

            # Use Tesseract if available
            result = subprocess.run(
                ["tesseract", str(temp_path), "stdout"],
                capture_output=True, text=True, timeout=15,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            temp_path.unlink(missing_ok=True)

            if result.returncode == 0 and result.stdout.strip():
                text = result.stdout.strip()
                if len(text) > 1000:
                    return f"Screen text (first 1000 chars):\n{text[:1000]}..."
                return f"Screen text:\n{text}"
            return "Could not extract text from the screen."
        except Exception as e:
            return f"OCR is not available: {e}. Install Tesseract for screen text reading."
    except Exception as e:
        return f"Failed to read screen text: {e}"

@tool(
    name="analyze_screen",
    description="Analyze the user's screen in real-time to answer a specific question using a Vision AI model.",
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question about the screen (e.g., 'What is this graph showing?', 'Read the error message')."
            }
        },
        "required": ["question"]
    }
)
def analyze_screen(question: str) -> str:
    """Capture screen and use vision model (Cloud or Local) to answer the question."""
    try:
        from core.llm_provider import llm_vision_generate
        
        # Capture screen
        img = ImageGrab.grab()
        
        # Convert to base64
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=70)
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        print(f"[VQA] Sending screen to Vision Model for: '{question}'")
        
        response = llm_vision_generate(question, img_b64)
        return f"Vision Model Analysis: {response}"
            
    except Exception as e:
        return f"Failed to analyze screen: {e}."
