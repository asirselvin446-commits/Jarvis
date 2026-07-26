"""
J.A.R.V.I.S. Messaging Plugin
Handles messaging tasks such as WhatsApp integration with instant keyboard automation.
"""

import os
import time
import urllib.parse
import webbrowser
import pyautogui
from core.tool_manager import tool

@tool(
    name="whatsapp_send_message",
    description="Opens WhatsApp and sends a message to a contact name or phone number instantly.",
    parameters={
        "type": "object",
        "properties": {
            "contact": {
                "type": "string",
                "description": "Name or phone number of the contact."
            },
            "message": {
                "type": "string",
                "description": "The message text to send."
            }
        },
        "required": ["contact", "message"]
    }
)
def whatsapp_send_message(contact: str, message: str) -> str:
    clean_contact = contact.strip()
    digits_only = ''.join(c for c in clean_contact if c.isdigit())

    # Case A: Phone number -> WhatsApp Web direct API
    if len(digits_only) >= 10:
        encoded_msg = urllib.parse.quote(message)
        url = f"https://web.whatsapp.com/send?phone={digits_only}&text={encoded_msg}"
        webbrowser.open(url)
        return f"Opened WhatsApp chat for {contact} with prepared message."

    # Case B: Contact Name -> Instant Keyboard Sequence Automation
    try:
        os.startfile("ms-whatsapp:")
    except Exception:
        webbrowser.open("https://web.whatsapp.com")

    time.sleep(2.0)  # Wait for app window to focus

    # Shortcut: Ctrl+F to open search in WhatsApp
    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.4)

    # Type contact name & open chat
    pyautogui.write(clean_contact, interval=0.02)
    time.sleep(0.6)
    pyautogui.press("enter")
    time.sleep(0.4)

    # Type message & send
    pyautogui.write(message, interval=0.02)
    time.sleep(0.2)
    pyautogui.press("enter")

    return f"Sent WhatsApp message to '{clean_contact}': '{message}'"
