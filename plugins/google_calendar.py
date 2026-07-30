"""
J.A.R.V.I.S. Google Calendar Plugin
Manages Google Calendar events via the Google Calendar API.

Setup:
1. Create a project at https://console.cloud.google.com
2. Enable the Google Calendar API
3. Create OAuth 2.0 credentials → download as 'credentials.json'
4. Place 'credentials.json' in ~/.jarvis/google/
5. First use will open a browser for OAuth consent

Requires: pip install google-auth google-auth-oauthlib google-api-python-client
"""

import os
import json
from datetime import datetime, timedelta
from core.tool_manager import tool

GOOGLE_DIR = os.path.join(os.path.expanduser("~"), ".jarvis", "google")
os.makedirs(GOOGLE_DIR, exist_ok=True)
CREDENTIALS_FILE = os.path.join(GOOGLE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(GOOGLE_DIR, "calendar_token.json")

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_calendar_service():
    """Authenticate and return a Google Calendar API service object."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        return None, "Google API libraries not installed. Run: pip install google-auth google-auth-oauthlib google-api-python-client"

    if not os.path.exists(CREDENTIALS_FILE):
        return None, (
            f"Google Calendar not configured. Download OAuth credentials from "
            f"Google Cloud Console and save as '{CREDENTIALS_FILE}'."
        )

    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                return None, f"OAuth flow failed: {e}"

        # Save the token for next run
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)
        return service, None
    except Exception as e:
        return None, f"Failed to build Calendar service: {e}"


@tool(
    name="get_calendar_events",
    description="Gets upcoming events from Google Calendar.",
    parameters={
        "type": "object",
        "properties": {
            "days_ahead": {
                "type": "integer",
                "description": "Number of days ahead to look for events.",
                "default": 7
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of events to return.",
                "default": 10
            }
        }
    }
)
def get_calendar_events(days_ahead: int = 7, max_results: int = 10) -> str:
    service, error = _get_calendar_service()
    if error:
        return error

    try:
        now = datetime.utcnow().isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"

        events_result = service.events().list(
            calendarId="primary",
            timeMin=now,
            timeMax=end,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        if not events:
            return f"No upcoming events in the next {days_ahead} days."

        lines = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            summary = event.get("summary", "(No title)")
            location = event.get("location", "")
            loc_str = f" at {location}" if location else ""
            lines.append(f"  • {start}: {summary}{loc_str}")

        return f"Upcoming events ({len(events)}):\n" + "\n".join(lines)

    except Exception as e:
        return f"Failed to fetch calendar events: {e}"


@tool(
    name="create_calendar_event",
    description="Creates a new event on Google Calendar.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Event title/summary."
            },
            "start_time": {
                "type": "string",
                "description": "Start time in ISO format (e.g., '2025-01-15T10:00:00') or natural language date."
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Duration of the event in minutes.",
                "default": 60
            },
            "description": {
                "type": "string",
                "description": "Optional event description.",
                "default": ""
            },
            "location": {
                "type": "string",
                "description": "Optional event location.",
                "default": ""
            }
        },
        "required": ["title", "start_time"]
    }
)
def create_calendar_event(title: str, start_time: str, duration_minutes: int = 60,
                          description: str = "", location: str = "") -> str:
    service, error = _get_calendar_service()
    if error:
        return error

    try:
        # Parse start time
        try:
            start_dt = datetime.fromisoformat(start_time)
        except ValueError:
            return f"Invalid start time format: '{start_time}'. Use ISO format like '2025-01-15T10:00:00'."

        end_dt = start_dt + timedelta(minutes=duration_minutes)

        event = {
            "summary": title,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"},
        }
        if description:
            event["description"] = description
        if location:
            event["location"] = location

        created = service.events().insert(calendarId="primary", body=event).execute()
        link = created.get("htmlLink", "")
        return f"Event '{title}' created on {start_dt.strftime('%Y-%m-%d %H:%M')}. Link: {link}"

    except Exception as e:
        return f"Failed to create event: {e}"


@tool(
    name="delete_calendar_event",
    description="Deletes a Google Calendar event by searching for it by title.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Title of the event to delete."
            }
        },
        "required": ["title"]
    }
)
def delete_calendar_event(title: str) -> str:
    service, error = _get_calendar_service()
    if error:
        return error

    try:
        now = datetime.utcnow().isoformat() + "Z"
        events_result = service.events().list(
            calendarId="primary",
            timeMin=now,
            maxResults=50,
            singleEvents=True,
            orderBy="startTime",
            q=title
        ).execute()

        events = events_result.get("items", [])
        if not events:
            return f"No upcoming event found with title matching '{title}'."

        # Delete the first match
        event = events[0]
        service.events().delete(calendarId="primary", eventId=event["id"]).execute()
        return f"Deleted event: '{event.get('summary', title)}'."

    except Exception as e:
        return f"Failed to delete event: {e}"
