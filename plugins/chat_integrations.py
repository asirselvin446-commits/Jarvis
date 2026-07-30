"""
J.A.R.V.I.S. Chat Integrations Plugin
Send and receive messages via Slack and Discord webhooks/bots.

Setup:
  Slack:   Set JARVIS_SLACK_WEBHOOK=https://hooks.slack.com/services/xxx
  Discord: Set JARVIS_DISCORD_WEBHOOK=https://discord.com/api/webhooks/xxx
"""

import os
import json
import requests
from core.tool_manager import tool

SLACK_WEBHOOK = os.environ.get("JARVIS_SLACK_WEBHOOK", "")
DISCORD_WEBHOOK = os.environ.get("JARVIS_DISCORD_WEBHOOK", "")


# ─── Slack ───────────────────────────────────────────────────────

@tool(
    name="send_slack_message",
    description="Sends a message to a Slack channel via webhook.",
    parameters={
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message to send to Slack."
            },
            "channel": {
                "type": "string",
                "description": "Optional channel name override (if webhook supports it).",
                "default": ""
            }
        },
        "required": ["message"]
    }
)
def send_slack_message(message: str, channel: str = "") -> str:
    if not SLACK_WEBHOOK:
        return ("Slack not configured. Set environment variable:\n"
                "  JARVIS_SLACK_WEBHOOK=https://hooks.slack.com/services/xxx")

    try:
        payload = {"text": message}
        if channel:
            payload["channel"] = f"#{channel}"

        resp = requests.post(SLACK_WEBHOOK, json=payload, timeout=10)
        if resp.status_code == 200 and resp.text == "ok":
            return f"Message sent to Slack: '{message[:50]}...'"
        else:
            return f"Slack webhook error: {resp.status_code} {resp.text[:100]}"

    except Exception as e:
        return f"Failed to send Slack message: {e}"


# ─── Discord ─────────────────────────────────────────────────────

@tool(
    name="send_discord_message",
    description="Sends a message to a Discord channel via webhook.",
    parameters={
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message to send to Discord."
            },
            "username": {
                "type": "string",
                "description": "Optional display name for the bot.",
                "default": "J.A.R.V.I.S."
            }
        },
        "required": ["message"]
    }
)
def send_discord_message(message: str, username: str = "J.A.R.V.I.S.") -> str:
    if not DISCORD_WEBHOOK:
        return ("Discord not configured. Set environment variable:\n"
                "  JARVIS_DISCORD_WEBHOOK=https://discord.com/api/webhooks/xxx")

    try:
        payload = {
            "content": message,
            "username": username
        }

        resp = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            return f"Message sent to Discord: '{message[:50]}...'"
        else:
            return f"Discord webhook error: {resp.status_code} {resp.text[:100]}"

    except Exception as e:
        return f"Failed to send Discord message: {e}"


# ─── Generic Chat Message ────────────────────────────────────────

@tool(
    name="send_chat_message",
    description="Sends a message to a configured chat platform (Slack or Discord). Auto-detects which is configured.",
    parameters={
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message to send."
            },
            "platform": {
                "type": "string",
                "description": "Which platform to send to: 'slack', 'discord', or 'auto' (sends to whichever is configured).",
                "default": "auto"
            }
        },
        "required": ["message"]
    }
)
def send_chat_message(message: str, platform: str = "auto") -> str:
    if platform == "slack" or (platform == "auto" and SLACK_WEBHOOK):
        return send_slack_message(message)
    elif platform == "discord" or (platform == "auto" and DISCORD_WEBHOOK):
        return send_discord_message(message)
    else:
        return ("No chat platform configured. Set one of:\n"
                "  JARVIS_SLACK_WEBHOOK=https://hooks.slack.com/services/xxx\n"
                "  JARVIS_DISCORD_WEBHOOK=https://discord.com/api/webhooks/xxx")
