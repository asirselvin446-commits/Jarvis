"""
J.A.R.V.I.S. Advanced Vision System
Object detection, UI element parsing, error detection, and screen understanding.
"""

import os
import base64
import logging
import json
from io import BytesIO
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

import pyautogui
from PIL import Image
import requests

logger = logging.getLogger(__name__)

# Ollama vision model configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
VISION_MODEL = "qwen2.5vl:3b"  # Can be swapped for other vision models
OLLAMA_VISION_ENDPOINT = f"{OLLAMA_URL}/api/generate"


class UIElementType(Enum):
    """Types of UI elements the vision system can detect."""
    BUTTON = "button"
    INPUT_FIELD = "input_field"
    CHECKBOX = "checkbox"
    DROPDOWN = "dropdown"
    MENU = "menu"
    DIALOG = "dialog"
    NOTIFICATION = "notification"
    ERROR = "error"
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    LINK = "link"
    UNKNOWN = "unknown"


@dataclass
class UIElement:
    """Represents a detected UI element."""
    type: UIElementType
    label: str
    position: Tuple[int, int]  # (x, y) coordinates
    size: Tuple[int, int]  # (width, height)
    confidence: float  # 0-1 confidence score
    interactive: bool = False
    text_content: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "label": self.label,
            "position": self.position,
            "size": self.size,
            "confidence": round(self.confidence, 2),
            "interactive": self.interactive,
            "text_content": self.text_content,
        }


@dataclass
class ScreenAnalysis:
    """Complete analysis of a screen."""
    raw_text: str
    description: str
    ui_elements: List[UIElement]
    error_detected: bool
    error_message: Optional[str] = None
    active_application: str = ""
    suggestions: List[str] = []
    timestamp: str = ""


class AdvancedVisionSystem:
    """Advanced vision capabilities for screen understanding."""
    
    def __init__(self):
        self.last_screenshot = None
        self.last_analysis = None
        self.analysis_history = []
        self.max_history = 20
    
    def capture_screen(self, quality: int = 85, max_width: int = 1280) -> str:
        """
        Capture screen and return as base64 encoded JPEG.
        
        Args:
            quality: JPEG quality (1-100)
            max_width: Maximum width for resize
            
        Returns:
            Base64 encoded image string
        """
        try:
            img = pyautogui.screenshot()
            self.last_screenshot = img
            
            # Resize for efficiency
            img = img.convert("RGB")
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
            
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=quality)
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            return ""
    
    def analyze_screen_comprehensive(self) -> ScreenAnalysis:
        """
        Perform comprehensive screen analysis including text, UI, and errors.
        
        Returns:
            ScreenAnalysis object with all detected information
        """
        b64_image = self.capture_screen()
        if not b64_image:
            return ScreenAnalysis(
                raw_text="",
                description="Failed to capture screen",
                ui_elements=[],
                error_detected=False,
            )
        
        # Run multiple analysis passes
        text_analysis = self._analyze_screen_text(b64_image)
        error_analysis = self._detect_errors(b64_image)
        ui_analysis = self._detect_ui_elements(b64_image)
        description = self._generate_screen_description(b64_image)
        
        analysis = ScreenAnalysis(
            raw_text=text_analysis,
            description=description,
            ui_elements=ui_analysis,
            error_detected=error_analysis["detected"],
            error_message=error_analysis.get("message"),
            suggestions=self._generate_suggestions(text_analysis, error_analysis),
        )
        
        self.last_analysis = analysis
        self.analysis_history.append(analysis)
        if len(self.analysis_history) > self.max_history:
            self.analysis_history.pop(0)
        
        return analysis
    
    def _analyze_screen_text(self, b64_image: str) -> str:
        """Extract all readable text from screen using OCR."""
        prompt = """Extract all readable text from this screen. Include:
- All visible text
- Button labels
- Menu items
- Window titles
- Input field labels
Format as a clean list without descriptions."""
        
        return self._call_vision_model(b64_image, prompt)
    
    def _detect_errors(self, b64_image: str) -> Dict[str, Any]:
        """Detect error dialogs, warnings, and exception messages."""
        prompt = """Analyze this screen for any error messages, warnings, or exceptions.
If found, provide:
1. Error type (e.g., "FileNotFoundError", "Warning", "Network Error")
2. Error message
3. Suggested resolution if visible

If no errors found, respond with "NO_ERRORS_DETECTED"."""
        
        response = self._call_vision_model(b64_image, prompt)
        
        if "NO_ERRORS_DETECTED" in response:
            return {"detected": False}
        
        return {
            "detected": True,
            "message": response.strip(),
        }
    
    def _detect_ui_elements(self, b64_image: str) -> List[UIElement]:
        """Detect interactive UI elements on screen."""
        prompt = """Identify all interactive UI elements on this screen.
For each element, provide: type (button|input|checkbox|dropdown|etc), label, approximate position (x,y in pixels), size, and text.
Format as JSON array only, no other text."""
        
        response = self._call_vision_model(b64_image, prompt)
        
        elements = []
        try:
            # Try to extract JSON from response
            data = json.loads(response)
            if isinstance(data, list):
                for item in data:
                    try:
                        element = UIElement(
                            type=UIElementType(item.get("type", "unknown")),
                            label=item.get("label", ""),
                            position=(item.get("x", 0), item.get("y", 0)),
                            size=(item.get("width", 0), item.get("height", 0)),
                            confidence=float(item.get("confidence", 0.8)),
                            interactive=item.get("interactive", True),
                            text_content=item.get("text", ""),
                        )
                        elements.append(element)
                    except (ValueError, KeyError) as e:
                        logger.warning(f"Failed to parse UI element: {e}")
        except json.JSONDecodeError:
            logger.warning("Failed to parse UI detection response as JSON")
        
        return elements
    
    def _generate_screen_description(self, b64_image: str) -> str:
        """Generate human-readable description of what's on screen."""
        prompt = """Provide a brief, natural-language description of what's currently displayed on this screen.
Include:
- Active applications and windows
- Main content being shown
- Key UI elements
Keep it concise (2-3 sentences)."""
        
        return self._call_vision_model(b64_image, prompt)
    
    def _generate_suggestions(self, text: str, error_analysis: Dict) -> List[str]:
        """Generate helpful suggestions based on screen content."""
        suggestions = []
        
        if error_analysis.get("detected"):
            suggestions.append("Error detected on screen - consider reading the error message aloud")
        
        if "password" in text.lower() or "login" in text.lower():
            suggestions.append("Login screen detected - verify credentials before proceeding")
        
        if "unsaved" in text.lower() or "save" in text.lower():
            suggestions.append("Unsaved changes detected - consider saving before closing")
        
        return suggestions[:3]  # Limit to top 3 suggestions
    
    def _call_vision_model(self, b64_image: str, prompt: str) -> str:
        """Call the Ollama vision model with image and prompt."""
        try:
            payload = {
                "model": VISION_MODEL,
                "prompt": prompt,
                "images": [b64_image],
                "stream": False,
                "options": {
                    "temperature": 0.2,  # Low temperature for consistent results
                    "top_p": 0.9,
                }
            }
            
            response = requests.post(
                OLLAMA_VISION_ENDPOINT,
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                return response.json().get("response", "")
            else:
                logger.error(f"Vision model error: {response.status_code} {response.text}")
                return ""
        except requests.exceptions.ConnectionError:
            logger.error("Failed to connect to Ollama service")
            return ""
        except Exception as e:
            logger.error(f"Vision model call failed: {e}")
            return ""
    
    def understand_ui_layout(self) -> Dict[str, Any]:
        """Analyze current UI layout and structure."""
        b64_image = self.capture_screen()
        if not b64_image:
            return {}
        
        prompt = """Analyze the UI layout of this screen and describe:
1. Overall layout structure (grid, sidebar, etc.)
2. Main content area description
3. Navigation elements
4. Top bar/header content
5. Status bar/footer content
Provide as a structured description."""
        
        layout = self._call_vision_model(b64_image, prompt)
        return {"layout_description": layout}
    
    def detect_app_changes(self) -> Dict[str, Any]:
        """Detect if the active application or major UI has changed."""
        if not self.last_analysis:
            return {"changed": False}
        
        current = self.analyze_screen_comprehensive()
        
        # Compare with previous analysis
        text_changed = current.raw_text != self.last_analysis.raw_text
        ui_changed = len(current.ui_elements) != len(self.last_analysis.ui_elements)
        error_state_changed = current.error_detected != self.last_analysis.error_detected
        
        changed = text_changed or ui_changed or error_state_changed
        
        return {
            "changed": changed,
            "text_changed": text_changed,
            "ui_changed": ui_changed,
            "error_state_changed": error_state_changed,
            "current_app": current.active_application,
        }
    
    def get_element_at_position(self, x: int, y: int) -> Optional[UIElement]:
        """Find UI element at specific screen position."""
        if not self.last_analysis:
            return None
        
        for element in self.last_analysis.ui_elements:
            ex, ey = element.position
            ew, eh = element.size
            
            if ex <= x <= ex + ew and ey <= y <= ey + eh:
                return element
        
        return None
    
    def get_clickable_elements(self) -> List[UIElement]:
        """Get all clickable UI elements from last analysis."""
        if not self.last_analysis:
            return []
        
        return [e for e in self.last_analysis.ui_elements if e.interactive]
    
    def export_analysis(self) -> str:
        """Export last analysis as JSON."""
        if not self.last_analysis:
            return "{}"
        
        return json.dumps({
            "timestamp": self.last_analysis.timestamp,
            "raw_text": self.last_analysis.raw_text,
            "description": self.last_analysis.description,
            "ui_elements": [e.to_dict() for e in self.last_analysis.ui_elements],
            "error_detected": self.last_analysis.error_detected,
            "error_message": self.last_analysis.error_message,
            "suggestions": self.last_analysis.suggestions,
        }, indent=2)


# Global instance
_vision_system = None


def get_vision_system() -> AdvancedVisionSystem:
    """Get or create global vision system instance."""
    global _vision_system
    if _vision_system is None:
        _vision_system = AdvancedVisionSystem()
    return _vision_system
