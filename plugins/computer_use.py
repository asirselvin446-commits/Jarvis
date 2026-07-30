"""
J.A.R.V.I.S. Computer Use Plugin
Autonomous vision-action loop that can perform ANY multi-step GUI task.
Uses qwen2.5-vl:3b to see the screen and decide what to click/type.

Examples:
  - "Open WhatsApp and text Chandru hi"
  - "Open YouTube and play Shape of You"
  - "Go to Gmail and compose an email"
"""

import os
import re
import json
import time
import base64
from io import BytesIO

import pyautogui
import requests
from PIL import Image

from core.tool_manager import tool

# ─── Config ──────────────────────────────────────────────────────
OLLAMA_VISION_URL = "http://localhost:11434/api/generate"
VISION_MODEL = "qwen2.5vl:3b"
MAX_STEPS = 10          # Safety limit: max actions per task
STEP_DELAY = 1.0        # Seconds to wait between actions for UI to update
VISION_RETRIES = 2      # Retry vision parsing this many times before giving up
SCREENSHOT_QUALITY = 70 # JPEG quality for faster base64 transmission

# Disable pyautogui's fail-safe pause for smoother automation
pyautogui.PAUSE = 0.3
pyautogui.FAILSAFE = True  # Keep failsafe ON (move mouse to corner to abort)


# Thumbnail dimensions used for vision processing
THUMBNAIL_W = 1024
THUMBNAIL_H = 576


def _capture_screen_base64() -> tuple:
    """Capture the full screen, resize for fast vision processing, and return (base64 JPEG, actual_w, actual_h, thumb_w, thumb_h)."""
    img = pyautogui.screenshot()
    actual_w, actual_h = img.size
    img = img.convert("RGB")
    img.thumbnail((THUMBNAIL_W, THUMBNAIL_H))
    thumb_w, thumb_h = img.size  # Actual thumbnail dimensions after aspect-ratio preservation
    
    buffered = BytesIO()
    img.save(buffered, format="JPEG", quality=SCREENSHOT_QUALITY)
    b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return b64, actual_w, actual_h, thumb_w, thumb_h


def _get_screen_size() -> tuple:
    """Get screen resolution."""
    return pyautogui.size()


def _ask_vision(screenshot_b64: str, prompt: str) -> str:
    """Send a screenshot + prompt to the vision model and get a response."""
    payload = {
        "model": VISION_MODEL,
        "prompt": prompt,
        "images": [screenshot_b64],
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 300
        }
    }
    
    try:
        resp = requests.post(OLLAMA_VISION_URL, json=payload, timeout=120)
        if resp.status_code == 200:
            return resp.json().get("response", "")
        return f"Vision API Error: {resp.status_code}"
    except Exception as e:
        return f"Vision API Connection Error: {e}"


def _parse_action(response_text: str) -> dict:
    """Extract the JSON action from the vision model's response."""
    # Try to find JSON in the response
    # Pattern 1: ```json ... ```
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if json_match:
        try:
            json_str = json_match.group(1).replace('\\\\', '\\')
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # Pattern 2: Raw JSON object
    json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', response_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    # Pattern 3: Try the whole response
    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError:
        pass
    
    # If nothing works, return error
    return {"action": "error", "detail": f"Could not parse action from: {response_text[:200]}"}


def _scale_coordinates(action: dict, actual_w: int, actual_h: int, thumb_w: int, thumb_h: int) -> dict:
    """Scale coordinates from thumbnail space to actual screen space."""
    if "x" in action and "y" in action:
        # The vision model sees the thumbnail, so its coordinates are in thumbnail space.
        # Scale them proportionally to actual screen resolution.
        scale_x = actual_w / thumb_w
        scale_y = actual_h / thumb_h
        action["x"] = int(int(action["x"]) * scale_x)
        action["y"] = int(int(action["y"]) * scale_y)
        # Clamp to screen bounds
        action["x"] = max(0, min(action["x"], actual_w - 1))
        action["y"] = max(0, min(action["y"], actual_h - 1))
    return action


def _execute_action(action: dict) -> str:
    """Execute a single action on the screen via pyautogui."""
    action_type = action.get("action", "").lower()
    
    try:
        if action_type == "click":
            x, y = int(action["x"]), int(action["y"])
            pyautogui.click(x, y)
            return f"Clicked at ({x}, {y})"
        
        elif action_type == "double_click":
            x, y = int(action["x"]), int(action["y"])
            pyautogui.doubleClick(x, y)
            return f"Double-clicked at ({x}, {y})"
        
        elif action_type == "right_click":
            x, y = int(action["x"]), int(action["y"])
            pyautogui.rightClick(x, y)
            return f"Right-clicked at ({x}, {y})"
        
        elif action_type == "type":
            if "x" in action and "y" in action:
                x, y = int(action["x"]), int(action["y"])
                pyautogui.click(x, y)
                time.sleep(0.3)
            text = action.get("text", "")
            pyautogui.typewrite(text, interval=0.03) if text.isascii() else pyautogui.write(text)
            return f"Typed: '{text}'"
        
        elif action_type == "hotkey":
            keys = action.get("keys", [])
            if isinstance(keys, str):
                keys = [k.strip() for k in keys.split("+")]
            pyautogui.hotkey(*keys)
            return f"Pressed hotkey: {'+'.join(keys)}"
        
        elif action_type == "press":
            key = action.get("key", "")
            pyautogui.press(key)
            return f"Pressed key: {key}"
        
        elif action_type == "scroll":
            direction = action.get("direction", "down")
            amount = int(action.get("amount", 3))
            if direction == "up":
                pyautogui.scroll(amount)
            else:
                pyautogui.scroll(-amount)
            return f"Scrolled {direction} by {amount}"
        
        elif action_type == "wait":
            seconds = float(action.get("seconds", 2))
            seconds = min(seconds, 5)  # Safety: max 5 second wait
            time.sleep(seconds)
            return f"Waited {seconds} seconds"
        
        elif action_type == "done":
            summary = action.get("summary", "Task completed.")
            return f"DONE: {summary}"
        
        elif action_type == "error":
            return f"Vision parsing error: {action.get('detail', 'unknown')}"
        
        else:
            return f"Unknown action type: {action_type}"
    
    except Exception as e:
        return f"Action execution error: {e}"


def _get_accessibility_context() -> str:
    """Get UI element names from the accessibility tree for more reliable interaction."""
    try:
        from core.accessibility import get_clickable_elements, format_element_summary
        elements = get_clickable_elements()
        if elements:
            summary = format_element_summary(elements, max_items=20)
            return f"\nAccessibility-detected UI elements (with exact screen coordinates):\n{summary}\n"
    except Exception as e:
        print(f"[ComputerUse] Accessibility fallback: {e}")
    return ""


def _build_vision_prompt(goal: str, step: int, history: list, screen_w: int, screen_h: int,
                         accessibility_context: str = "") -> str:
    """Build the prompt for the vision model, enriched with accessibility data."""
    history_text = ""
    if history:
        history_text = "\n".join([f"  Step {i+1}: {h}" for i, h in enumerate(history)])
        history_text = f"\nActions taken so far:\n{history_text}\n"
    
    return f"""You are an AI agent controlling a Windows PC. Your goal is to complete the user's task by performing ONE action at a time.

TASK: {goal}

Screen resolution: {screen_w}x{screen_h} pixels.
Current step: {step} of {MAX_STEPS}.
{history_text}
{accessibility_context}
Look at the screenshot carefully. Decide the SINGLE NEXT action to take.
If accessibility data is provided above, PREFER using those exact coordinates — they are more accurate than visual estimates.

RULES:
1. Return ONLY a JSON object with the action. No explanation.
2. Use EXACT pixel coordinates (x, y) based on what you see in the screenshot.
3. CRITICAL: When using 'type', you MUST provide 'x' and 'y' coordinates of the text box / input field to click before typing! Example: {{"action": "type", "x": 500, "y": 80, "text": "shape of you"}}. NEVER type without x and y!
4. CRITICAL: Do NOT type the entire task string. Type only the relevant search query or URL into the targeted input field.
5. If the task is already complete, return {{"action": "done", "summary": "description of what was accomplished"}}.
6. Available actions:
   - {{"action": "click", "x": 100, "y": 200}} — click at coordinates
   - {{"action": "double_click", "x": 100, "y": 200}} — double-click
   - {{"action": "right_click", "x": 100, "y": 200}} — right-click
   - {{"action": "type", "x": 500, "y": 80, "text": "hello"}} — MUST include x, y of the input field to click before typing!
   - {{"action": "press", "key": "enter"}} — press a key (enter, tab, escape, backspace, etc.)
   - {{"action": "hotkey", "keys": ["ctrl", "a"]}} — press key combination
   - {{"action": "scroll", "direction": "down", "amount": 3}} — scroll
   - {{"action": "wait", "seconds": 2}} — wait for something to load
   - {{"action": "done", "summary": "what was accomplished"}} — task is finished

Return ONLY the JSON object. Example: {{"action": "type", "x": 500, "y": 80, "text": "youtube.com"}}"""


def computer_use_loop(goal: str) -> str:
    """
    Main autonomous loop. Takes screenshots, asks vision model for actions,
    executes them, and repeats until done or safety limit reached.
    Includes retry logic for vision parse failures and coordinate scaling.
    """
    screen_w, screen_h = _get_screen_size()
    history = []
    
    print(f"[ComputerUse] Starting task: '{goal}' (max {MAX_STEPS} steps)")
    
    for step in range(1, MAX_STEPS + 1):
        # 1. Capture screenshot (returns base64 + dimension info)
        screenshot_b64, actual_w, actual_h, thumb_w, thumb_h = _capture_screen_base64()
        
        # 2. Get accessibility context (UI element names + coordinates)
        accessibility_context = _get_accessibility_context()
        
        # 3. Ask vision model what to do (with retry on parse failure)
        action = None
        for attempt in range(1, VISION_RETRIES + 1):
            prompt = _build_vision_prompt(goal, step, history, thumb_w, thumb_h, accessibility_context)
            vision_response = _ask_vision(screenshot_b64, prompt)
            print(f"[ComputerUse] Step {step} (attempt {attempt}) — Vision response: {vision_response[:150]}")
            
            # 3. Parse the action
            action = _parse_action(vision_response)
            
            # If parse succeeded (not an error), break out of retry loop
            if action.get("action") != "error":
                break
            elif attempt < VISION_RETRIES:
                print(f"[ComputerUse] Step {step} — Parse failed, retrying...")
                time.sleep(0.5)  # Brief pause before retry
        
        print(f"[ComputerUse] Step {step} — Parsed action: {action}")
        
        # 4. Scale coordinates from thumbnail to actual screen resolution
        if action.get("action") not in ("done", "error", "press", "hotkey", "wait"):
            action = _scale_coordinates(action, actual_w, actual_h, thumb_w, thumb_h)
        
        # 5. Execute the action
        result = _execute_action(action)
        print(f"[ComputerUse] Step {step} — Result: {result}")
        history.append(result)
        
        # 6. Check if done
        if action.get("action") == "done" or result.startswith("DONE:"):
            summary = action.get("summary", "Task completed.")
            print(f"[ComputerUse] Task completed in {step} steps: {summary}")
            return summary
        
        # 7. Wait for UI to update before next screenshot
        time.sleep(STEP_DELAY)
    
    # Safety limit reached
    final_msg = f"Reached safety limit of {MAX_STEPS} steps. Actions taken: {'; '.join(history)}"
    print(f"[ComputerUse] {final_msg}")
    return final_msg


# ─── Register as a Tool ──────────────────────────────────────────

@tool(
    name="computer_use",
    description=(
        "Performs ANY multi-step task on the PC by autonomously controlling the mouse and keyboard. "
        "Uses AI vision to see the screen and decide what to click, type, or press. "
        "Use this for complex tasks that require multiple steps, like: "
        "'open WhatsApp and text Chandru hi', "
        "'open YouTube and play Shape of You', "
        "'go to Gmail and compose an email'. "
        "Do NOT use this for simple one-step actions like opening an app or doing a Google search — "
        "use the specific tools for those."
    ),
    parameters={
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "The complete task to accomplish, described in detail (e.g., 'Open WhatsApp, find the contact named Chandru, and send the message: hi')."
            }
        },
        "required": ["goal"]
    }
)
def computer_use(goal: str) -> str:
    """Entry point for the computer use tool."""
    return computer_use_loop(goal)
