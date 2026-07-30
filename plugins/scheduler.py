"""
J.A.R.V.I.S. Scheduler & Timer Plugin
Handles background timers, alarms, and reminders.
"""

import time
import threading
import datetime
import re
from core.tool_manager import tool
from core.voice_engine import VoiceEngine

_voice = None
_active_timers = []  # Track active timers/alarms for potential cancellation

def _get_voice():
    global _voice
    if _voice is None:
        try:
            _voice = VoiceEngine()
        except Exception:
            _voice = None
    return _voice


def _play_alert_sound():
    """Play a system alert sound to get attention."""
    try:
        import winsound
        # Play 3 ascending beeps
        for freq in [800, 1000, 1200]:
            winsound.Beep(freq, 300)
            time.sleep(0.1)
    except Exception:
        pass  # Fallback: no sound on non-Windows or if winsound fails


def _format_duration(total_seconds: int) -> str:
    """Format seconds into a human-readable string."""
    hours, remainder = divmod(total_seconds, 3600)
    mins, secs = divmod(remainder, 60)
    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if mins > 0:
        parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
    if secs > 0 or not parts:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    return " and ".join(parts)


@tool(
    name="set_timer",
    description="Sets a countdown timer for a specified number of seconds or minutes.",
    parameters={
        "type": "object",
        "properties": {
            "duration_seconds": {
                "type": "integer",
                "description": "Duration of timer in seconds."
            },
            "label": {
                "type": "string",
                "description": "Optional name or description for the timer.",
                "default": "Timer"
            }
        },
        "required": ["duration_seconds"]
    }
)
def set_timer(duration_seconds: int, label: str = "Timer") -> str:
    timer_id = len(_active_timers)
    cancel_event = threading.Event()

    def _timer_worker():
        # Use event.wait() instead of time.sleep() so timer can be cancelled
        cancelled = cancel_event.wait(timeout=max(1, duration_seconds))
        if cancelled:
            return  # Timer was cancelled
        message = f"Sir, your timer for {label} has finished!"
        print(f"[JARVIS Timer] {message}")
        _play_alert_sound()
        v = _get_voice()
        if v:
            v.speak(message)

    _active_timers.append({"id": timer_id, "label": label, "cancel": cancel_event, "type": "timer"})
    threading.Thread(target=_timer_worker, daemon=True).start()
    time_str = _format_duration(duration_seconds)
    return f"Timer set for {label} ({time_str})."


@tool(
    name="set_alarm",
    description="Sets an alarm for a specific time of day (e.g., '7:30 AM', '14:00', '9pm').",
    parameters={
        "type": "object",
        "properties": {
            "time_str": {
                "type": "string",
                "description": "The target time (e.g., '7:30 AM', '14:00', '9pm', '6:00')."
            },
            "label": {
                "type": "string",
                "description": "Optional label for the alarm.",
                "default": "Alarm"
            }
        },
        "required": ["time_str"]
    }
)
def set_alarm(time_str: str, label: str = "Alarm") -> str:
    """Set an alarm for a specific clock time."""
    now = datetime.datetime.now()

    # Parse various time formats
    target_time = None
    time_str_clean = time_str.strip().upper()

    # Try common formats
    formats = [
        "%I:%M %p",   # 7:30 AM
        "%I:%M%p",    # 7:30AM
        "%I %p",      # 7 AM
        "%I%p",       # 7AM
        "%H:%M",      # 14:00
        "%H",         # 14
    ]

    for fmt in formats:
        try:
            parsed = datetime.datetime.strptime(time_str_clean, fmt)
            target_time = now.replace(
                hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0
            )
            break
        except ValueError:
            continue

    if target_time is None:
        return f"Sorry, I couldn't understand the time '{time_str}'. Try formats like '7:30 AM', '14:00', or '9pm'."

    # If the target time has already passed today, set it for tomorrow
    if target_time <= now:
        target_time += datetime.timedelta(days=1)

    delay_seconds = (target_time - now).total_seconds()
    cancel_event = threading.Event()
    timer_id = len(_active_timers)

    def _alarm_worker():
        cancelled = cancel_event.wait(timeout=max(1, delay_seconds))
        if cancelled:
            return
        message = f"Sir, your alarm for {label} is going off! It's {target_time.strftime('%I:%M %p')}."
        print(f"[JARVIS Alarm] {message}")
        _play_alert_sound()
        v = _get_voice()
        if v:
            v.speak(message)

    _active_timers.append({"id": timer_id, "label": label, "cancel": cancel_event, "type": "alarm"})
    threading.Thread(target=_alarm_worker, daemon=True).start()

    formatted_time = target_time.strftime("%I:%M %p")
    duration = _format_duration(int(delay_seconds))
    return f"Alarm '{label}' set for {formatted_time} ({duration} from now)."


@tool(
    name="set_reminder",
    description="Sets a reminder message to speak aloud after a given delay in minutes.",
    parameters={
        "type": "object",
        "properties": {
            "delay_minutes": {
                "type": "integer",
                "description": "Number of minutes to wait before reminding."
            },
            "reminder_text": {
                "type": "string",
                "description": "The message/reminder to speak."
            }
        },
        "required": ["delay_minutes", "reminder_text"]
    }
)
def set_reminder(delay_minutes: int, reminder_text: str) -> str:
    seconds = max(1, delay_minutes * 60)
    cancel_event = threading.Event()
    timer_id = len(_active_timers)

    def _reminder_worker():
        cancelled = cancel_event.wait(timeout=seconds)
        if cancelled:
            return
        message = f"Sir, reminder: {reminder_text}"
        print(f"[JARVIS Reminder] {message}")
        _play_alert_sound()
        v = _get_voice()
        if v:
            v.speak(message)

    _active_timers.append({"id": timer_id, "label": reminder_text, "cancel": cancel_event, "type": "reminder"})
    threading.Thread(target=_reminder_worker, daemon=True).start()
    duration = _format_duration(seconds)
    return f"Reminder set for '{reminder_text}' in {duration}."

