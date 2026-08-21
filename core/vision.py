"""
J.A.R.V.I.S. Vision Agent
Uses Gemini Flash 2.5 (cloud) or Qwen2.5-VL 3B via Ollama (local) to understand the screen.
Upgraded to a Continuous Perception Engine providing structured UI observation,
dialog detection, loading state tracking, and post-action change verification.
"""

import os
import json
import base64
import requests
from io import BytesIO
import pyautogui
import numpy as np
from PIL import Image

from core.base_agent import BaseAgent, AgentResult
from core.tool_manager import ToolManager, tool
from core.memory import MemoryManager
from core.planner import Planner

OLLAMA_VISION_URL = "http://localhost:11434/api/generate"
VISION_MODEL_LOCAL = "qwen2.5vl:3b"

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
VISION_MODEL_CLOUD = "gemini-flash-latest"

class VisionAgent(BaseAgent):
    def __init__(self, tool_manager: ToolManager, memory: MemoryManager):
        super().__init__("vision", "Vision agent capable of continuous perception and screen analysis", 
                         ["read_screen_text", "describe_screen", "find_ui_element"], 
                         tool_manager, memory)
        self.planner = Planner()
        
    def can_handle(self, task: str) -> float:
        task_lower = task.lower()
        if any(kw in task_lower for kw in ["screen", "see", "look", "read the screen", "what's on"]):
            return 0.95
        return 0.0

    def execute(self, task: str, context: str = "") -> AgentResult:
        tool_schemas = [self.tool_manager.get_schema(n) for n in self.tools if self.tool_manager.get_schema(n)]
        plan_result = self.planner.plan_and_select_tools(task, context, tool_schemas)

        if plan_result["type"] == "tools":
            tool_results = self._execute_tool_calls(plan_result["tool_calls"])
            try:
                response_stream = self.planner.evaluate_result_stream(task, tool_results)
                response = ""
            except Exception:
                response_stream = None
                response = ". ".join(str(tr.get("result", "Done")) for tr in tool_results)
            all_success = all(tr.get("verified_success", False) for tr in tool_results)
            return AgentResult(success=all_success, response=response, agent_name=self.name,
                               tool_results=tool_results, response_stream=response_stream)
        elif plan_result["type"] == "response":
            return AgentResult(success=True, response=plan_result["content"], agent_name=self.name)
        else:
            return AgentResult(success=False, response=plan_result.get("content", "Error"), agent_name=self.name)

    def _capture_screen_base64(self, quality=85) -> str:
        """Capture the screen and return it as a base64 encoded JPEG string."""
        img = pyautogui.screenshot()
        img = img.convert("RGB")
        img.thumbnail((1280, 720)) 
        
        buffered = BytesIO()
        img.save(buffered, format="JPEG", quality=quality)
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def _analyze_screen_local(self, prompt: str, b64_image: str) -> str:
        payload = {
            "model": VISION_MODEL_LOCAL,
            "prompt": prompt,
            "images": [b64_image],
            "stream": False,
            "options": {"temperature": 0.1}
        }
        try:
            resp = requests.post(OLLAMA_VISION_URL, json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json().get("response", "")
            return f"Vision Model Error: {resp.status_code} {resp.text}"
        except Exception as e:
            return f"Failed to connect to Vision Model: {e}"

    def _analyze_screen_cloud(self, prompt: str, b64_image: str) -> str:
        from core.llm_provider import _get_api_key
        api_key = _get_api_key()
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_image
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1
            }
        }
        url = f"{GEMINI_API_BASE}/models/{VISION_MODEL_CLOUD}:generateContent?key={api_key}"
        try:
            resp = requests.post(url, json=payload, timeout=45)
            resp.raise_for_status()
            data = resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                return "Failed to parse Gemini Vision response."
        except Exception as e:
            raise RuntimeError(f"Cloud Vision Error: {e}")

    def analyze_screen(self, prompt: str) -> str:
        """Send a screenshot and a prompt to the best available Vision model."""
        b64_image = self._capture_screen_base64()
        from core.llm_provider import is_online
        import logging
        logger = logging.getLogger("jarvis.vision")
        
        if is_online():
            try:
                logger.debug("[VISION] Using Cloud Vision (Gemini)")
                return self._analyze_screen_cloud(prompt, b64_image)
            except Exception as e:
                # The request URL (with ?key=) rides along in HTTPError text.
                from core.redaction import redact_text
                logger.warning("[VISION] Cloud failed (%s), falling back to local",
                               redact_text(str(e)))
                
        logger.debug("[VISION] Using Local Vision (Ollama)")
        return self._analyze_screen_local(prompt, b64_image)

    def perceive_ui(self) -> dict:
        """
        Continuous Perception Engine method:
        Analyzes active screen to determine app, dialogs, popups, loading status, and interactive controls.
        """
        prompt = """
Analyze this screen state and return a valid JSON object with the following fields:
{
  "active_app": "name of primary active window/app",
  "active_window": "title of the focused window",
  "has_dialog_or_popup": true/false,
  "popup_description": "description of any dialog/popup if present, else empty",
  "is_loading": true/false,
  "visible_buttons": ["list", "of", "button", "labels"],
  "visible_inputs": ["list", "of", "placeholder", "or", "input", "labels"]
}
Return ONLY JSON.
"""
        raw_res = self.analyze_screen(prompt)
        try:
            # Extract JSON block
            if "```json" in raw_res:
                raw_res = raw_res.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_res:
                raw_res = raw_res.split("```")[1].split("```")[0].strip()
            return json.loads(raw_res)
        except Exception:
            return {
                "active_app": "Unknown",
                "active_window": "Desktop",
                "has_dialog_or_popup": False,
                "popup_description": "",
                "is_loading": False,
                "visible_buttons": [],
                "visible_inputs": []
            }

    def detect_ui_changes(self, before_b64: str, after_b64: str) -> dict:
        """
        Compare before and after screenshots to verify if an action produced expected UI change.
        Uses pixel-level difference analysis for fast, reliable detection.
        """
        try:
            from PIL import ImageChops
            import io
            
            # Decode both images
            before_img = Image.open(io.BytesIO(base64.b64decode(before_b64))).convert("RGB")
            after_img = Image.open(io.BytesIO(base64.b64decode(after_b64))).convert("RGB")
            
            # Resize to same dimensions for comparison
            size = (640, 360)
            before_img = before_img.resize(size)
            after_img = after_img.resize(size)
            
            # Compute per-pixel difference
            diff = ImageChops.difference(before_img, after_img)
            diff_np = np.array(diff)
            
            # Calculate percentage of pixels that changed significantly (threshold > 30/255)
            significant_change = np.mean(diff_np > 30)  # Fraction of pixel-channels above threshold
            changed = significant_change > 0.02  # More than 2% of the image changed
            
            summary = f"{significant_change*100:.1f}% of pixels changed significantly."
            if changed:
                summary += " UI state update detected."
            else:
                summary += " No meaningful visual change."
            
            return {"ui_changed": changed, "summary": summary, "change_pct": round(significant_change * 100, 1)}
            
        except Exception as e:
            # Fallback: if image processing fails, assume changed
            return {"ui_changed": True, "summary": f"Could not compare screenshots: {e}"}


# ─── Global Instance for Tool Handlers ──────────────────────────────────────────

_global_vision_instance = None

def set_vision_instance(instance: VisionAgent):
    global _global_vision_instance
    _global_vision_instance = instance


@tool(
    name="read_screen_text",
    description="Captures the screen and extracts text, reading what is currently visible on the monitor.",
    parameters={"type": "object", "properties": {}}
)
def read_screen_text() -> str:
    if not _global_vision_instance:
        return "Error: Vision module not initialized."
    return _global_vision_instance.analyze_screen("Extract all readable text from this screen.")

@tool(
    name="describe_screen",
    description="Captures the screen and provides a detailed description of what is visible (e.g., UI elements, open apps).",
    parameters={"type": "object", "properties": {}}
)
def describe_screen() -> str:
    if not _global_vision_instance:
        return "Error: Vision module not initialized."
    return _global_vision_instance.analyze_screen("Describe what is on this screen in detail. What applications are open? Are there any errors?")

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
    if not _global_vision_instance:
        return "Error: Vision module not initialized."
    prompt = f"Find the '{element_description}' on the screen. Return a JSON object with its approximate x and y coordinates (0-100% relative to screen dimensions)."
    return _global_vision_instance.analyze_screen(prompt)
