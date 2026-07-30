"""
J.A.R.V.I.S. Environment Monitor
Continuously monitors system state so the voice pipeline can adapt.
Detects: audio playing, headphones, fullscreen apps, meetings, noise levels, etc.
"""

import threading
import time
import logging
from typing import Optional

logger = logging.getLogger("jarvis.environment")


class EnvironmentState:
    """Snapshot of the current system environment."""

    def __init__(self):
        self.music_playing: bool = False
        self.headphones_connected: bool = False
        self.mic_muted: bool = False
        self.active_window: str = ""
        self.active_window_title: str = ""
        self.is_fullscreen: bool = False
        self.is_meeting: bool = False
        self.is_gaming: bool = False
        self.is_presentation: bool = False
        self.cpu_usage: float = 0.0
        self.memory_usage_mb: float = 0.0
        self.noise_level_db: float = -60.0
        self.timestamp: float = time.time()

    def to_dict(self) -> dict:
        return {
            "music_playing": self.music_playing,
            "headphones_connected": self.headphones_connected,
            "mic_muted": self.mic_muted,
            "active_window": self.active_window,
            "active_window_title": self.active_window_title,
            "is_fullscreen": self.is_fullscreen,
            "is_meeting": self.is_meeting,
            "is_gaming": self.is_gaming,
            "is_presentation": self.is_presentation,
            "cpu_usage": self.cpu_usage,
            "memory_usage_mb": self.memory_usage_mb,
            "noise_level_db": self.noise_level_db,
        }


class EnvironmentMonitor:
    """
    Background monitor that periodically samples system state.
    The voice pipeline consults this to adapt its behavior:
      - Suppress wake word during fullscreen gaming (unless headphones)
      - Lower TTS volume during meetings
      - Adjust silence thresholds based on ambient noise
    """

    # Window titles that indicate a meeting
    MEETING_KEYWORDS = [
        "zoom", "teams", "google meet", "webex", "slack huddle",
        "discord call", "skype", "meets",
    ]

    # Window titles / process names that indicate gaming
    GAMING_INDICATORS = [
        "steam", "epic games", "riot", "valorant", "minecraft",
        "fortnite", "apex", "unity", "unreal",
    ]

    # Presentation indicators
    PRESENTATION_KEYWORDS = [
        "powerpoint slideshow", "google slides", "presentation mode",
        "keynote", "prezi",
    ]

    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._state = EnvironmentState()
        self._lock = threading.Lock()

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self):
        """Start background monitoring."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="env-monitor"
        )
        self._thread.start()
        logger.info("Environment monitor started (poll=%.1fs).", self.poll_interval)

    def stop(self):
        """Stop background monitoring."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("Environment monitor stopped.")

    @property
    def state(self) -> EnvironmentState:
        """Get the latest environment state (thread-safe copy)."""
        with self._lock:
            return self._state

    # ── Decision helpers ─────────────────────────────────────────

    def should_suppress_wake(self) -> bool:
        """Should the wake word be suppressed right now?"""
        s = self.state
        # Suppress during fullscreen without headphones
        if s.is_fullscreen and not s.headphones_connected:
            return True
        # Suppress during presentations
        if s.is_presentation:
            return True
        return False

    def should_lower_volume(self) -> bool:
        """Should TTS be quieter?"""
        s = self.state
        return s.is_meeting

    def get_noise_adjusted_threshold(self, base_threshold: float) -> float:
        """Adjust the wake word threshold based on ambient noise."""
        s = self.state
        noise = s.noise_level_db

        if noise > -20:
            # Very noisy — increase threshold to avoid false triggers
            return min(base_threshold + 0.2, 0.9)
        elif noise > -30:
            # Moderate noise
            return min(base_threshold + 0.1, 0.8)
        else:
            return base_threshold

    # ── Monitor loop ─────────────────────────────────────────────

    def _monitor_loop(self):
        """Periodically sample system state."""
        while self._running:
            try:
                new_state = EnvironmentState()
                self._check_audio_state(new_state)
                self._check_active_window(new_state)
                self._check_system_resources(new_state)

                with self._lock:
                    self._state = new_state

            except Exception as e:
                logger.error("Environment monitor error: %s", e)

            time.sleep(self.poll_interval)

    # ── State checkers ───────────────────────────────────────────

    def _check_audio_state(self, state: EnvironmentState):
        """Check if audio is playing and headphone state."""
        try:
            from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
            from comtypes import CLSCTX_ALL

            # Check if any audio sessions are active
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                try:
                    meter = session._ctl.QueryInterface(IAudioMeterInformation)
                    peak = meter.GetPeakValue()
                    if peak > 0.01:
                        state.music_playing = True
                        break
                except Exception:
                    continue

            # Check audio endpoint for headphones
            try:
                import ctypes
                from ctypes import wintypes

                # Use the default audio endpoint to check if it's headphones
                devices = AudioUtilities.GetSpeakers()
                if devices:
                    endpoint = devices.GetDefaultAudioEndpoint(0, 0) if hasattr(devices, 'GetDefaultAudioEndpoint') else None
                    # Heuristic: if device name contains "headphone" or "earbuds"
                    try:
                        from pycaw.pycaw import IMMDevice
                        name = devices.GetId()
                        if name and any(kw in name.lower() for kw in ["headphone", "earbuds", "airpods", "buds"]):
                            state.headphones_connected = True
                    except Exception:
                        pass
            except Exception:
                pass

        except ImportError:
            pass
        except Exception as e:
            logger.debug("Audio state check error: %s", e)

    def _check_active_window(self, state: EnvironmentState):
        """Check the currently focused window."""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()

            # Get window title
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.lower()
            state.active_window_title = buf.value

            # Get process name
            try:
                import psutil

                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                proc = psutil.Process(pid.value)
                state.active_window = proc.name()
            except Exception:
                state.active_window = ""

            # Check if fullscreen
            try:
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                screen_w = user32.GetSystemMetrics(0)
                screen_h = user32.GetSystemMetrics(1)
                window_w = rect.right - rect.left
                window_h = rect.bottom - rect.top
                state.is_fullscreen = (window_w >= screen_w and window_h >= screen_h)
            except Exception:
                pass

            # Check for meetings
            state.is_meeting = any(kw in title for kw in self.MEETING_KEYWORDS)

            # Check for gaming
            state.is_gaming = any(
                kw in title or kw in state.active_window.lower()
                for kw in self.GAMING_INDICATORS
            )

            # Check for VS Code active file (Proactive Context Fetching)
            if "code" in state.active_window.lower() or "visual studio code" in title:
                # Typically format: "filename - project - Visual Studio Code"
                parts = title.split(" - ")
                if len(parts) >= 2:
                    try:
                        from core.message_bus import get_message_bus
                        bus = get_message_bus()
                        bus.publish("context_update", "environment", {"active_file": parts[0]})
                    except Exception:
                        pass

            # Check for presentations
            state.is_presentation = any(kw in title for kw in self.PRESENTATION_KEYWORDS)

        except Exception as e:
            logger.debug("Active window check error: %s", e)

    def _check_system_resources(self, state: EnvironmentState):
        """Check CPU and memory usage."""
        try:
            import psutil

            state.cpu_usage = psutil.cpu_percent(interval=0)
            process = psutil.Process()
            state.memory_usage_mb = process.memory_info().rss / (1024 * 1024)
        except Exception as e:
            logger.debug("System resource check error: %s", e)
