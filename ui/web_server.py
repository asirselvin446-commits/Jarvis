import os
import sys
import traceback
from flask import Flask, render_template, request, jsonify
from core.os_kernel import OSKernel
from core.voice_engine import VoiceEngine
import threading
import logging
import time

# Disable Flask default logging for cleaner terminal output
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Determine correct base path (works both in dev and PyInstaller)
if getattr(sys, 'frozen', False):
    # PyInstaller extracts to sys._MEIPASS. Since we added data to ui/templates, it's at sys._MEIPASS/ui
    BASE_DIR = os.path.join(sys._MEIPASS, 'ui')
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))

kernel = OSKernel()
voice = VoiceEngine()

# Track voice state for the UI
_voice_state = {"listening": False, "last_transcript": "", "last_error": ""}
_voice_lock = threading.Lock()


def _on_voice_recognized(text):
    """Called when voice engine recognizes speech."""
    with _voice_lock:
        _voice_state["listening"] = False
        _voice_state["last_transcript"] = text


def _on_voice_error(err):
    with _voice_lock:
        _voice_state["listening"] = False
        _voice_state["last_error"] = str(err)


def _on_listening_start():
    with _voice_lock:
        _voice_state["listening"] = True
        _voice_state["last_transcript"] = ""
        _voice_state["last_error"] = ""


def _on_listening_stop():
    with _voice_lock:
        _voice_state["listening"] = False


# Wire up callbacks
voice.on_recognized = _on_voice_recognized
voice.on_error = _on_voice_error
voice.on_listening_start = _on_listening_start
voice.on_listening_stop = _on_listening_stop


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/command', methods=['POST'])
def handle_command():
    try:
        data = request.json
        text = data.get('text', '')
        if not text:
            return jsonify({"success": False, "response": "Empty command", "action": ""})

        result = kernel.process_command(text)
        # Also speak the response
        voice.speak(result.get("response", ""))
        return jsonify(result)
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Flask API Error: {error_trace}")
        return jsonify({"success": False, "response": f"Internal Error: {str(e)}", "action": ""})


@app.route('/api/voice/start', methods=['POST'])
def voice_start():
    """Start listening for voice input."""
    try:
        voice.start_listening()
        return jsonify({"success": True, "status": "listening"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/voice/status', methods=['GET'])
def voice_status():
    """Poll voice recognition status."""
    with _voice_lock:
        return jsonify({
            "listening": _voice_state["listening"],
            "transcript": _voice_state["last_transcript"],
            "error": _voice_state["last_error"]
        })


@app.route('/api/voice/speak', methods=['POST'])
def voice_speak():
    """Speak text aloud via TTS."""
    try:
        data = request.json
        text = data.get('text', '')
        if text:
            voice.speak(text)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def start_server(port=5000):
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)


def start_server_in_thread(port=5000):
    thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    thread.start()
    return thread
