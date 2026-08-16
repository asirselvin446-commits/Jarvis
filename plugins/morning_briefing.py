"""
J.A.R.V.I.S. Morning Briefing Plugin
Delivers a comprehensive daily briefing via voice at a configurable time.
Registers itself as a CronEngine job on first load.
"""

import datetime
import logging
from core.tool_manager import tool

logger = logging.getLogger("jarvis.briefing")

_briefing_registered = False


def _gather_briefing() -> str:
    """Aggregate information from all available sources into a briefing string."""
    sections = []
    now = datetime.datetime.now()
    greeting = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Good evening"
    sections.append(f"{greeting}, sir. Here is your briefing for {now.strftime('%A, %B %d')}.")

    # 1. Weather
    try:
        from plugins.weather import get_weather_brief
        weather = get_weather_brief()
        if weather and "error" not in str(weather).lower():
            sections.append(f"Weather: {weather}")
    except Exception:
        pass

    # 2. Calendar
    try:
        from plugins.google_calendar import get_calendar_events
        events = get_calendar_events("today")
        if events and "no events" not in events.lower() and "error" not in events.lower():
            sections.append(f"Your schedule: {events[:300]}")
        else:
            sections.append("You have no events scheduled today.")
    except Exception:
        sections.append("Calendar is not configured.")

    # 3. Unread Emails
    try:
        from plugins.email_client import read_emails
        emails = read_emails(count=3)
        if emails and "error" not in str(emails).lower():
            sections.append(f"Recent emails: {str(emails)[:300]}")
    except Exception:
        pass

    # 4. Battery
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery:
            pct = battery.percent
            plugged = "plugged in" if battery.power_plugged else "on battery"
            sections.append(f"Battery is at {pct}%, {plugged}.")
    except Exception:
        pass

    # 5. System Health
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        sections.append(f"System health: CPU {cpu}%, RAM {ram}%.")
    except Exception:
        pass

    # 6. Active sub-agents
    try:
        from core.os_kernel import OSKernel
        kernel = OSKernel()
        agents = kernel.get_sub_agent_status()
        running = [a for a in agents if a["status"] == "running"]
        if running:
            sections.append(f"You have {len(running)} background agent(s) still running.")
    except Exception:
        pass

    sections.append("That's all for now, sir. Have a productive day.")
    return " ".join(sections)


def _deliver_briefing():
    """Speak the briefing aloud and publish to the message bus."""
    briefing_text = _gather_briefing()
    logger.info(f"[MorningBriefing] Delivering briefing: {briefing_text[:100]}...")

    # Publish to bus for UI/logging
    try:
        from core.message_bus import get_message_bus
        get_message_bus().publish("morning_briefing", "briefing_plugin", {"text": briefing_text})
    except Exception:
        pass

    # Speak via proactive intelligence's _speak pathway
    try:
        from core.proactive_intelligence import get_proactive_intelligence
        pi = get_proactive_intelligence()
        pi._speak(briefing_text)
    except Exception as e:
        logger.error(f"[MorningBriefing] Failed to speak: {e}")
        print(f"[MorningBriefing] {briefing_text}")


def _should_deliver_now() -> bool:
    """Only deliver if it's roughly the target time (8:30 AM ± 5 minutes)."""
    now = datetime.datetime.now()
    return now.hour == 8 and 25 <= now.minute <= 35


def _cron_check():
    """Called by the CronEngine. Only delivers if it's the right time."""
    if _should_deliver_now():
        _deliver_briefing()


def register_briefing_cron(kernel=None):
    """Register the morning briefing cron job on an already-built kernel.

    NOTE: This is invoked by ``OSKernel._register_core_cron_jobs()`` after the
    cron loop is live. It must NOT be called at import time, and must never
    construct an OSKernel itself — doing so caused a re-entrant kernel-init
    cascade (dozens of Gateways / Cron loops all firing this job in a loop).
    """
    global _briefing_registered
    if _briefing_registered:
        return
    if kernel is None:
        return
    try:
        kernel.cron.add_job("morning_briefing", 60, _cron_check)
        _briefing_registered = True
        logger.info("[MorningBriefing] Registered morning briefing cron job.")
    except Exception as e:
        logger.error(f"[MorningBriefing] Failed to register cron: {e}")


@tool(
    name="trigger_briefing",
    description="Manually triggers the daily morning briefing right now, regardless of time.",
    parameters={"type": "object", "properties": {}}
)
def trigger_briefing() -> str:
    briefing = _gather_briefing()

    try:
        from core.proactive_intelligence import get_proactive_intelligence
        pi = get_proactive_intelligence()
        pi._speak(briefing)
    except Exception:
        pass

    return briefing
