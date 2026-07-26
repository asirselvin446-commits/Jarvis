"""
J.A.R.V.I.S. File Manager Plugin
Open folders and create directories.
"""

import os
from core.tool_manager import tool
from config import DIRECTORIES, USER_HOME

@tool(
    name="open_folder",
    description="Opens a specific folder by name (e.g., 'desktop', 'downloads', 'documents').",
    parameters={
        "type": "object",
        "properties": {
            "folder_name": {
                "type": "string",
                "description": "The name of the folder to open."
            }
        },
        "required": ["folder_name"]
    }
)
def open_folder(folder_name: str) -> str:
    name_clean = folder_name.strip().lower()
    folder_path = DIRECTORIES.get(name_clean)

    if not folder_path:
        aliases = {
            "c drive": "C:\\",
            "d drive": "D:\\",
            "e drive": "E:\\",
            "root": "C:\\",
            "user": USER_HOME,
            "home": USER_HOME,
            "profile": USER_HOME,
            "pics": os.path.join(USER_HOME, "Pictures"),
            "photos": os.path.join(USER_HOME, "Pictures"),
            "vids": os.path.join(USER_HOME, "Videos"),
            "movies": os.path.join(USER_HOME, "Videos"),
            "docs": os.path.join(USER_HOME, "Documents"),
        }
        folder_path = aliases.get(name_clean)

    if not folder_path:
        if os.path.exists(folder_name):
            folder_path = folder_name
        else:
            possible = os.path.join(USER_HOME, folder_name)
            if os.path.exists(possible):
                folder_path = possible

    if not folder_path or not os.path.exists(folder_path):
        return f"The '{folder_name}' folder was not found on your system."

    try:
        os.startfile(folder_path)
        return f"Successfully opened {folder_name} folder."
    except Exception as e:
        return f"Couldn't open folder: {e}"

@tool(
    name="create_folder",
    description="Creates a new folder at a specified location (default: desktop).",
    parameters={
        "type": "object",
        "properties": {
            "folder_name": {
                "type": "string",
                "description": "The name of the new folder to create."
            },
            "location": {
                "type": "string",
                "description": "The location to create the folder in (e.g., 'desktop', 'documents').",
                "default": "desktop"
            }
        },
        "required": ["folder_name"]
    }
)
def create_folder(folder_name: str, location: str = "desktop") -> str:
    folder_name = folder_name.strip()
    location = location.strip().lower()

    base_path = DIRECTORIES.get(location, DIRECTORIES["desktop"])
    full_path = os.path.join(base_path, folder_name)

    try:
        os.makedirs(full_path, exist_ok=True)
        return f"Created folder '{folder_name}' on your {location}."
    except Exception as e:
        return f"Couldn't create folder: {e}"
