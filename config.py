"""
J.A.R.V.I.S. Configuration
Central configuration for the voice assistant.
"""

import os

# ─── Assistant Identity ────────────────────────────────────────────
ASSISTANT_NAME = "Jarvis"
WAKE_WORD = "jarvis"
GREETING = "Hello! I am Jarvis, your personal assistant. How can I help you?"

# ─── Voice Settings ────────────────────────────────────────────────
VOICE_RATE = 175          # Words per minute (default ~200)
VOICE_VOLUME = 1.0        # 0.0 to 1.0
VOICE_ID = 0              # 0 = male, 1 = female (SAPI5 index)

# ─── Speech Recognition (Legacy — used by old VoiceEngine) ────
LISTEN_TIMEOUT = 5        # Seconds to wait for speech
PHRASE_TIME_LIMIT = 10    # Max seconds for a single phrase
ENERGY_THRESHOLD = 300    # Mic sensitivity (lower = more sensitive)
DYNAMIC_ENERGY = True     # Auto-adjust to ambient noise

# ─── Voice Pipeline (New — Always-On System) ──────────────────
# Wake Word Detection (VAD + STT)
# Energy thresholds for VAD are handled by STT settings

# Streaming STT (faster-whisper on CPU)
STT_MODEL = "base.en"                # Whisper model size
STT_DEVICE = "cpu"                   # Keep GPU free for Qwen LLM
STT_COMPUTE_TYPE = "int8"            # Fast CPU inference

# Intelligent Silence Detection
SILENCE_THRESHOLD_SHORT = 1.5        # Seconds — speech likely done
SILENCE_THRESHOLD_LONG = 3.0         # Seconds — mid-sentence pause tolerance
ENERGY_SILENCE_DB = -40              # dB threshold for "silence"
MAX_RECORDING_SECONDS = 30.0         # Hard cap on single utterance

# Conversation Session
FOLLOW_UP_WINDOW = 8.0               # Seconds for follow-up (no wake word)
CONVERSATION_TIMEOUT = 30.0          # Seconds before context expires
CONVERSATION_HISTORY_TURNS = 10      # Turns to keep in active context

# TTS (edge-tts neural voice)
TTS_VOICE = "en-US-GuyNeural"        # Microsoft neural voice
TTS_RATE = "+10%"                    # Speech speed adjustment
TTS_VOLUME = "+0%"                   # Volume adjustment

USER_HOME = os.path.expanduser("~")
LOCAL_APP = os.path.join(USER_HOME, "AppData", "Local")
ROAMING_APP = os.path.join(USER_HOME, "AppData", "Roaming")
PROGRAM_FILES = os.environ.get("ProgramFiles", r"C:\Program Files")
PROGRAM_FILES_X86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

# ─── Default Applications ──────────────────────────────────────────
# Set to None to use system default, or specify an app name from APP_PATHS (e.g., "brave", "firefox")
DEFAULT_BROWSER = "chrome"

# ─── Application Paths ────────────────────────────────────────────
# Maps spoken name → executable path or system command
APP_PATHS = {
    # Built-in Windows apps
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "wordpad": "wordpad.exe",
    "task manager": "taskmgr.exe",
    "control panel": "control",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "file explorer": "explorer.exe",
    "snipping tool": "snippingtool.exe",
    "settings": "ms-settings:",
    "device manager": "devmgmt.msc",

    # Dynamic app paths
    "chrome": os.path.join(PROGRAM_FILES, "Google", "Chrome", "Application", "chrome.exe"),
    "google chrome": os.path.join(PROGRAM_FILES, "Google", "Chrome", "Application", "chrome.exe"),
    "firefox": os.path.join(PROGRAM_FILES, "Mozilla Firefox", "firefox.exe"),
    "edge": os.path.join(PROGRAM_FILES_X86, "Microsoft", "Edge", "Application", "msedge.exe"),
    "microsoft edge": os.path.join(PROGRAM_FILES_X86, "Microsoft", "Edge", "Application", "msedge.exe"),
    "vs code": os.path.join(LOCAL_APP, "Programs", "Microsoft VS Code", "Code.exe"),
    "visual studio code": os.path.join(LOCAL_APP, "Programs", "Microsoft VS Code", "Code.exe"),
    "discord": f'"{os.path.join(LOCAL_APP, "Discord", "Update.exe")}" --processStart Discord.exe',
    "spotify": os.path.join(ROAMING_APP, "Spotify", "Spotify.exe"),
    "steam": os.path.join(PROGRAM_FILES_X86, "Steam", "steam.exe"),
    "vlc": os.path.join(PROGRAM_FILES, "VideoLAN", "VLC", "vlc.exe"),
    "obs": os.path.join(PROGRAM_FILES, "obs-studio", "bin", "64bit", "obs64.exe"),
    "telegram": os.path.join(ROAMING_APP, "Telegram Desktop", "Telegram.exe"),
    "whatsapp": os.path.join(LOCAL_APP, "WhatsApp", "WhatsApp.exe"),
    "brave": os.path.join(PROGRAM_FILES, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    "youtube": "https://www.youtube.com",
    "facebook": "https://www.facebook.com",
    "reddit": "https://www.reddit.com",
}

# ─── Common Directories ───────────────────────────────────────────
DIRECTORIES = {
    "desktop": os.path.join(USER_HOME, "Desktop"),
    "downloads": os.path.join(USER_HOME, "Downloads"),
    "documents": os.path.join(USER_HOME, "Documents"),
    "pictures": os.path.join(USER_HOME, "Pictures"),
    "music": os.path.join(USER_HOME, "Music"),
    "videos": os.path.join(USER_HOME, "Videos"),
}

# ─── Screenshot Settings ──────────────────────────────────────────
SCREENSHOT_DIR = os.path.join(USER_HOME, "Pictures", "JarvisScreenshots")

# ─── UI Settings ──────────────────────────────────────────────────
WINDOW_TITLE = "J.A.R.V.I.S. — Voice Assistant"
WINDOW_SIZE = "950x680"
MIN_WIDTH = 750
MIN_HEIGHT = 550
