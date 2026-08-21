"""
J.A.R.V.I.S. Universal Action Layer
Provides application-agnostic, low-level action primitives for GUI and OS control.
Every action returns a standardized ActionResult containing execution status,
confidence scores, retry recommendations, and timing metadata.
"""

import time
import os
import sys
import logging
import subprocess
import shutil
import pyautogui
import pyperclip
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger("jarvis.universal_actions")

# Enable PyAutoGUI safety pauses and failsafe
pyautogui.PAUSE = 0.2
pyautogui.FAILSAFE = True


class ActionResult:
    """Standardized result wrapper for all universal UI and system actions."""

    def __init__(
        self,
        success: bool,
        failure_reason: str = "",
        confidence: float = 1.0,
        retry_recommendation: bool = False,
        execution_time: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.success = success
        self.failure_reason = failure_reason
        self.confidence = confidence
        self.retry_recommendation = retry_recommendation
        self.execution_time = execution_time
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "failure_reason": self.failure_reason,
            "confidence": self.confidence,
            "retry_recommendation": self.retry_recommendation,
            "execution_time": self.execution_time,
            "metadata": self.metadata
        }

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else f"FAILED ({self.failure_reason})"
        return f"<ActionResult {status} | time={self.execution_time:.3f}s>"


class UniversalActions:
    """
    Universal GUI and OS Action Primitive Registry.
    Executes raw atomic actions with safety bounds and timing tracking.
    """

    @staticmethod
    def _time_action(func, *args, **kwargs) -> Tuple[bool, str, float, Any]:
        start = time.time()
        try:
            res = func(*args, **kwargs)
            elapsed = time.time() - start
            return True, "", elapsed, res
        except Exception as e:
            elapsed = time.time() - start
            return False, str(e), elapsed, None

    @classmethod
    def click(cls, x: int, y: int, clicks: int = 1, button: str = 'left') -> ActionResult:
        """Click at absolute screen coordinates."""
        start = time.time()
        try:
            screen_w, screen_h = pyautogui.size()
            if not (0 <= x <= screen_w and 0 <= y <= screen_h):
                return ActionResult(
                    success=False,
                    failure_reason=f"Coordinates ({x}, {y}) out of screen bounds ({screen_w}x{screen_h})",
                    confidence=0.0,
                    retry_recommendation=False,
                    execution_time=time.time() - start
                )
            pyautogui.click(x=x, y=y, clicks=clicks, button=button)
            return ActionResult(
                success=True,
                confidence=0.95,
                execution_time=time.time() - start,
                metadata={"x": x, "y": y, "button": button, "clicks": clicks}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Click failed: {e}",
                confidence=0.0,
                retry_recommendation=True,
                execution_time=time.time() - start
            )

    @classmethod
    def double_click(cls, x: int, y: int) -> ActionResult:
        """Double click at absolute screen coordinates."""
        return cls.click(x=x, y=y, clicks=2, button='left')

    @classmethod
    def right_click(cls, x: int, y: int) -> ActionResult:
        """Right click at absolute screen coordinates."""
        return cls.click(x=x, y=y, clicks=1, button='right')

    @classmethod
    def move_mouse(cls, x: int, y: int, duration: float = 0.2) -> ActionResult:
        """Smoothly move mouse pointer to target coordinates."""
        start = time.time()
        try:
            pyautogui.moveTo(x=x, y=y, duration=duration)
            return ActionResult(
                success=True,
                confidence=1.0,
                execution_time=time.time() - start,
                metadata={"x": x, "y": y}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Move mouse failed: {e}",
                execution_time=time.time() - start
            )

    @classmethod
    def drag(cls, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> ActionResult:
        """Drag mouse pointer from start coordinates to end coordinates."""
        start = time.time()
        try:
            pyautogui.moveTo(start_x, start_y)
            pyautogui.dragTo(end_x, end_y, duration=duration, button='left')
            return ActionResult(
                success=True,
                confidence=0.9,
                execution_time=time.time() - start,
                metadata={"start": (start_x, start_y), "end": (end_x, end_y)}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Drag failed: {e}",
                retry_recommendation=True,
                execution_time=time.time() - start
            )

    @classmethod
    def scroll(cls, clicks: int = 3, direction: str = 'down', x: Optional[int] = None, y: Optional[int] = None) -> ActionResult:
        """Scroll mouse wheel vertically up or down."""
        start = time.time()
        try:
            amount = -abs(clicks) * 100 if direction.lower() == 'down' else abs(clicks) * 100
            pyautogui.scroll(amount, x=x, y=y)
            return ActionResult(
                success=True,
                confidence=0.9,
                execution_time=time.time() - start,
                metadata={"clicks": clicks, "direction": direction}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Scroll failed: {e}",
                execution_time=time.time() - start
            )

    @classmethod
    def press(cls, key: str, presses: int = 1) -> ActionResult:
        """Press a single key (e.g. 'enter', 'tab', 'esc', 'backspace')."""
        start = time.time()
        try:
            pyautogui.press(key, presses=presses)
            return ActionResult(
                success=True,
                confidence=1.0,
                execution_time=time.time() - start,
                metadata={"key": key, "presses": presses}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Key press failed for '{key}': {e}",
                execution_time=time.time() - start
            )

    @classmethod
    def hotkey(cls, *keys: str) -> ActionResult:
        """Trigger key combination (e.g. 'ctrl', 'c' or 'alt', 'tab')."""
        start = time.time()
        try:
            pyautogui.hotkey(*keys)
            return ActionResult(
                success=True,
                confidence=1.0,
                execution_time=time.time() - start,
                metadata={"keys": keys}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Hotkey failed for {keys}: {e}",
                execution_time=time.time() - start
            )

    @classmethod
    def type_text(cls, text: str, interval: float = 0.01,
                  force_keystrokes: bool = False) -> ActionResult:
        """Enter text into the focused control, exactly as given.

        Uses a clipboard paste by default. Synthesising one key event per
        character is unreliable at speed — keys get dropped or repeated
        ("tides" arriving as "sssss") — and newlines are frequently swallowed.
        A paste is a single atomic insert, so the text lands verbatim,
        newlines included, regardless of length or typing speed.

        The user's clipboard is saved and restored around the paste.

        Args:
            text: The exact text to enter.
            interval: Per-character delay for the keystroke path only.
            force_keystrokes: Skip the clipboard and synthesise keys. Needed
                where a paste is rejected (some password boxes and terminals).
        """
        start = time.time()
        if not text:
            return ActionResult(success=True, confidence=1.0,
                                execution_time=time.time() - start,
                                metadata={"text_length": 0})

        if not force_keystrokes:
            ok, err = cls._paste_preserving_clipboard(text)
            if ok:
                return ActionResult(
                    success=True,
                    confidence=0.98,
                    execution_time=time.time() - start,
                    metadata={"text_length": len(text), "method": "clipboard"}
                )
            logger.warning("[UniversalActions] Clipboard paste failed (%s); "
                           "falling back to keystrokes.", err)

        try:
            cls._write_with_newlines(text, interval)
            return ActionResult(
                success=True,
                confidence=0.85,
                execution_time=time.time() - start,
                metadata={"text_length": len(text), "method": "keystrokes"}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Type text failed: {e}",
                retry_recommendation=True,
                execution_time=time.time() - start
            )

    @staticmethod
    def _paste_preserving_clipboard(text: str) -> Tuple[bool, str]:
        """Paste text via the clipboard, leaving the user's clipboard as it was.

        Returns (succeeded, error). Verifies the clipboard actually took the
        text before pressing Ctrl+V, so a clipboard held open by another
        process degrades to the keystroke path instead of pasting stale content.
        """
        saved = None
        try:
            try:
                saved = pyperclip.paste()
            except Exception:
                saved = None  # nothing to restore; not fatal

            pyperclip.copy(text)
            time.sleep(0.12)
            if pyperclip.paste() != text:
                return False, "clipboard did not accept the text"

            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.15)
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            if saved is not None:
                try:
                    time.sleep(0.05)
                    pyperclip.copy(saved)
                except Exception:
                    pass

    @staticmethod
    def _write_with_newlines(text: str, interval: float) -> None:
        """Type text via key events, pressing Enter for newlines.

        pyautogui.write() ignores "\\n", so multi-line text would otherwise
        arrive as one run-on line.
        """
        for i, line in enumerate(text.replace("\r\n", "\n").split("\n")):
            if i:
                pyautogui.press("enter")
            if line:
                pyautogui.write(line, interval=interval)

    @classmethod
    def paste(cls, text: str) -> ActionResult:
        """Paste text via clipboard for instant input of long strings or special characters."""
        start = time.time()
        try:
            pyperclip.copy(text)
            time.sleep(0.05)
            pyautogui.hotkey('ctrl', 'v')
            return ActionResult(
                success=True,
                confidence=0.98,
                execution_time=time.time() - start,
                metadata={"text_length": len(text)}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Paste failed: {e}",
                retry_recommendation=True,
                execution_time=time.time() - start
            )

    @classmethod
    def copy(cls) -> ActionResult:
        """Copy active selection to clipboard and return text."""
        start = time.time()
        try:
            pyperclip.copy("")
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.1)
            content = pyperclip.paste()
            return ActionResult(
                success=True,
                confidence=0.9,
                execution_time=time.time() - start,
                metadata={"content": content}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Copy failed: {e}",
                execution_time=time.time() - start
            )

    @classmethod
    def wait_until(cls, condition_func, timeout: float = 5.0, poll_interval: float = 0.3) -> ActionResult:
        """Poll condition_func until it returns truthy value or times out."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                res = condition_func()
                if res:
                    return ActionResult(
                        success=True,
                        confidence=1.0,
                        execution_time=time.time() - start,
                        metadata={"result": res}
                    )
            except Exception:
                pass
            time.sleep(poll_interval)
        return ActionResult(
            success=False,
            failure_reason=f"Wait condition timed out after {timeout}s",
            confidence=0.0,
            retry_recommendation=True,
            execution_time=time.time() - start
        )

    @classmethod
    def capture_screen(cls, region: Optional[Tuple[int, int, int, int]] = None) -> ActionResult:
        """Capture screenshot returning PIL Image in metadata."""
        start = time.time()
        try:
            img = pyautogui.screenshot(region=region)
            return ActionResult(
                success=True,
                confidence=1.0,
                execution_time=time.time() - start,
                metadata={"image": img, "size": img.size}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Capture screen failed: {e}",
                execution_time=time.time() - start
            )

    @classmethod
    def find_element(cls, label: str, ui_model: Optional[Any] = None) -> ActionResult:
        """Locate element on screen matching label using UIModel / Accessibility / OCR."""
        start = time.time()
        try:
            if ui_model is None:
                from core.ui_model import UIModel
                ui_model = UIModel.capture_current_state()

            element = ui_model.find_element_by_text(label)
            if element:
                return ActionResult(
                    success=True,
                    confidence=element.get("confidence", 0.85),
                    execution_time=time.time() - start,
                    metadata={"element": element}
                )
            return ActionResult(
                success=False,
                failure_reason=f"Element '{label}' not found on active screen",
                confidence=0.0,
                retry_recommendation=True,
                execution_time=time.time() - start
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Find element failed: {e}",
                execution_time=time.time() - start
            )

    @classmethod
    def verify_element(cls, label: str, expected_state: str = "visible") -> ActionResult:
        """Verify if target element exists / is visible on screen."""
        res = cls.find_element(label)
        if expected_state.lower() == "visible":
            return res
        elif expected_state.lower() in ["disappeared", "hidden", "absent"]:
            return ActionResult(
                success=not res.success,
                failure_reason="" if not res.success else f"Element '{label}' is still visible",
                confidence=0.9,
                execution_time=res.execution_time
            )
        return res

    @classmethod
    def focus_window(cls, window_title: str) -> ActionResult:
        """Bring target window to front by title match."""
        start = time.time()
        try:
            ps_script = f"""
            $win = Get-Process | Where-Object {{ $_.MainWindowTitle -like "*{window_title}*" }} | Select-Object -First 1
            if ($win) {{
                $h = $win.MainWindowHandle
                Add-Type @"
                    using System;
                    using System.Runtime.InteropServices;
                    public class Win32 {{
                        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
                        [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
                    }}
"@
                [Win32]::ShowWindow($h, 9)
                [Win32]::SetForegroundWindow($h)
                Write-Output "OK"
            }} else {{
                Write-Output "NOT_FOUND"
            }}
            """
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True, text=True, timeout=5
            )
            out = result.stdout.strip()
            if "OK" in out:
                return ActionResult(
                    success=True,
                    confidence=0.95,
                    execution_time=time.time() - start,
                    metadata={"title": window_title}
                )
            return ActionResult(
                success=False,
                failure_reason=f"Window matching '{window_title}' not found",
                retry_recommendation=True,
                execution_time=time.time() - start
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Focus window error: {e}",
                execution_time=time.time() - start
            )

    @classmethod
    def switch_window(cls) -> ActionResult:
        """Alt+Tab to switch active window."""
        return cls.hotkey('alt', 'tab')

    @classmethod
    def close_window(cls) -> ActionResult:
        """Alt+F4 to close current window."""
        return cls.hotkey('alt', 'f4')

    @classmethod
    def open_application(cls, app_name: str) -> ActionResult:
        """Launch desktop application via app_commands / tool manager."""
        start = time.time()
        try:
            from core.tool_manager import ToolManager
            tm = ToolManager()
            res = tm.execute_tool("open_application", {"app_name": app_name})
            return ActionResult(
                success=True,
                confidence=0.9,
                execution_time=time.time() - start,
                metadata={"response": str(res)}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Open app failed: {e}",
                execution_time=time.time() - start
            )

    @classmethod
    def open_url(cls, url: str) -> ActionResult:
        """Open web URL in default browser."""
        start = time.time()
        try:
            import webbrowser
            if not url.startswith("http"):
                url = "https://" + url
            webbrowser.open(url)
            return ActionResult(
                success=True,
                confidence=0.95,
                execution_time=time.time() - start,
                metadata={"url": url}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Open URL failed: {e}",
                execution_time=time.time() - start
            )

    @classmethod
    def select_item(cls, item_text: str) -> ActionResult:
        """Select item by text using click / keyboard navigation."""
        res = cls.find_element(item_text)
        if res.success and "element" in res.metadata:
            el = res.metadata["element"]
            return cls.click(el["x"], el["y"])
        # Fallback to typing item text
        return cls.type_text(item_text)

    @classmethod
    def hover(cls, x: int, y: int) -> ActionResult:
        """Hover mouse over coordinates."""
        return cls.move_mouse(x, y, duration=0.2)

    @classmethod
    def upload_file(cls, file_path: str) -> ActionResult:
        """Paste file path into Windows Open File dialog and press Enter."""
        start = time.time()
        try:
            if not os.path.exists(file_path):
                return ActionResult(
                    success=False,
                    failure_reason=f"File path does not exist: {file_path}",
                    execution_time=time.time() - start
                )
            abs_path = os.path.abspath(file_path)
            # Paste path and hit enter
            cls.paste(abs_path)
            time.sleep(0.2)
            cls.press('enter')
            return ActionResult(
                success=True,
                confidence=0.9,
                execution_time=time.time() - start,
                metadata={"file_path": abs_path}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                failure_reason=f"Upload file failed: {e}",
                execution_time=time.time() - start
            )

    @classmethod
    def download_file(cls, target_dir: Optional[str] = None) -> ActionResult:
        """Trigger download hotkey (Ctrl+S) or save."""
        return cls.hotkey('ctrl', 's')
