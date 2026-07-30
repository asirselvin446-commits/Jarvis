"""
J.A.R.V.I.S. Screen Monitor
Background thread that periodically captures and indexes screen state,
so the agent "knows" what's on screen before being asked.
Stores recent screen context in memory for faster responses.
"""

import time
import threading
from datetime import datetime
from typing import Optional, List
from collections import deque


class ScreenState:
    """A snapshot of the screen state at a point in time."""

    def __init__(self, ocr_text: str = "", ui_elements: list = None,
                 active_window: str = "", timestamp: str = ""):
        self.ocr_text = ocr_text
        self.ui_elements = ui_elements or []
        self.active_window = active_window
        self.timestamp = timestamp or datetime.now().isoformat()

    def summary(self) -> str:
        """Get a brief summary of the screen state."""
        parts = []
        if self.active_window:
            parts.append(f"Active: {self.active_window}")
        if self.ocr_text:
            snippet = self.ocr_text[:200].replace("\n", " ")
            parts.append(f"Text: {snippet}")
        if self.ui_elements:
            parts.append(f"UI elements: {len(self.ui_elements)}")
        return " | ".join(parts) if parts else "No screen data"


class ScreenMonitor:
    """
    Background service that periodically captures screen state.
    
    - Captures OCR text every N seconds
    - Tracks active window changes
    - Stores recent states for context
    """

    def __init__(self, interval_seconds: int = 30, max_history: int = 10):
        self._interval = interval_seconds
        self._max_history = max_history
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._history: deque = deque(maxlen=max_history)
        self._lock = threading.Lock()
        self._last_active_window = ""

    def start(self):
        """Start the background screen monitor."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print(f"[ScreenMonitor] Started (interval={self._interval}s)")

    def stop(self):
        """Stop the background monitor."""
        self._running = False
        print("[ScreenMonitor] Stopped")

    def get_current_state(self) -> Optional[ScreenState]:
        """Get the most recent screen state."""
        with self._lock:
            return self._history[-1] if self._history else None

    def get_recent_states(self, n: int = 3) -> List[ScreenState]:
        """Get the N most recent screen states."""
        with self._lock:
            return list(self._history)[-n:]

    def get_context_summary(self) -> str:
        """Get a text summary for the LLM context."""
        state = self.get_current_state()
        if not state:
            return ""
        return f"[Screen: {state.summary()}]"

    def _get_active_window_title(self) -> str:
        """Get the title of the active/foreground window."""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return ""

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                # Get active window
                active_window = self._get_active_window_title()

                # Only do full OCR if window changed or periodically
                do_ocr = (active_window != self._last_active_window)
                self._last_active_window = active_window

                ocr_text = ""
                ui_elements = []

                if do_ocr:
                    # OCR the screen (lightweight)
                    try:
                        from core.ocr_engine import ocr_screen
                        ocr_text = ocr_screen()
                    except Exception as e:
                        print(f"[ScreenMonitor] OCR error: {e}")

                # Create state snapshot
                state = ScreenState(
                    ocr_text=ocr_text,
                    ui_elements=ui_elements,
                    active_window=active_window
                )

                with self._lock:
                    self._history.append(state)

            except Exception as e:
                print(f"[ScreenMonitor] Monitor error: {e}")

            time.sleep(self._interval)

    @property
    def is_running(self) -> bool:
        return self._running


# Global singleton
_monitor_instance: Optional[ScreenMonitor] = None
_monitor_lock = threading.Lock()


def get_screen_monitor(auto_start: bool = False) -> ScreenMonitor:
    """Get or create the global screen monitor singleton."""
    global _monitor_instance
    if _monitor_instance is None:
        with _monitor_lock:
            if _monitor_instance is None:
                _monitor_instance = ScreenMonitor()
                if auto_start:
                    _monitor_instance.start()
    return _monitor_instance
