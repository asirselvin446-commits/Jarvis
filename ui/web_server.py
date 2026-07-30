"""
J.A.R.V.I.S. Web Server
Flask server with WebSocket support for real-time voice pipeline communication.
Replaces the old polling-based voice API with event-driven WebSocket streaming.
"""

import os
import sys
import json
import traceback
import threading
import logging
import time

from flask import Flask, render_template, request, jsonify

logger = logging.getLogger("jarvis.web_server")

# Disable Flask default logging for cleaner terminal output
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

# Determine correct base path (works both in dev and PyInstaller)
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.join(sys._MEIPASS, "ui")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

# ── Core systems (initialized lazily) ────────────────────────────
_kernel = None
_pipeline = None
_conversation = None
_performance = None
_environment = None
_ws_clients = []
_ws_lock = threading.Lock()


def _get_kernel():
    global _kernel
    if _kernel is None:
        from core.os_kernel import OSKernel
        _kernel = OSKernel()
    return _kernel


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from core.voice_pipeline import VoicePipeline
        from core.conversation_manager import ConversationManager
        from core.performance_monitor import get_performance_monitor
        from core.environment_monitor import EnvironmentMonitor
        import config

        global _conversation, _performance, _environment

        _conversation = ConversationManager(
            max_turns=config.CONVERSATION_HISTORY_TURNS,
            conversation_timeout=config.CONVERSATION_TIMEOUT,
        )
        _performance = get_performance_monitor()
        _environment = EnvironmentMonitor()

        _pipeline = VoicePipeline(
            stt_model=config.STT_MODEL,
            stt_device=config.STT_DEVICE,
            tts_voice=config.TTS_VOICE,
            tts_rate=config.TTS_RATE,
            follow_up_window=config.FOLLOW_UP_WINDOW,
            conversation_timeout=config.CONVERSATION_TIMEOUT,
        )

        # ── Wire pipeline callbacks to WebSocket broadcast ───────
        _pipeline.on_state_change = _broadcast_state_change
        _pipeline.on_partial_transcript = _broadcast_partial_transcript
        _pipeline.on_final_transcript = _broadcast_final_transcript
        _pipeline.on_response = _broadcast_response
        _pipeline.on_error = _broadcast_error

        # ── Wire command handler through conversation manager ────
        def _handle_command(text: str) -> dict:
            _performance.start_timer("total_response")
            _performance.start_timer("processing_latency")
            _performance.record_command()

            # Process through conversation manager
            turn_info = _conversation.add_user_turn(text)

            if turn_info["type"] == "cancellation":
                _conversation.add_assistant_turn("Cancelled.")
                _performance.stop_timer("processing_latency")
                _performance.stop_timer("total_response")
                return {"success": True, "response": "Cancelled.", "action": "cancel"}

            if turn_info["type"] == "correction":
                _performance.record_correction()
                text = turn_info["text"]  # Use the corrected text

            # Get conversation context for the LLM
            context = _conversation.get_context_for_llm()

            # Process through the orchestrator with conversation context
            kernel = _get_kernel()
            result = kernel.orchestrator.process_command(text, conversation_context=context)

            # Record the response
            _conversation.add_assistant_turn(result.get("response", "Done."))

            _performance.stop_timer("processing_latency")
            _performance.stop_timer("total_response")

            return result

        _pipeline.command_handler = _handle_command

        # Start the environment monitor
        _environment.start()

    return _pipeline


# ── WebSocket broadcast helpers ──────────────────────────────────

def _broadcast(event: dict):
    """Broadcast a JSON event to all connected WebSocket clients."""
    msg = json.dumps(event)
    with _ws_lock:
        dead = []
        for ws in _ws_clients:
            try:
                ws.send(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_clients.remove(ws)


def _broadcast_state_change(state: str):
    _broadcast({"type": "state_change", "state": state})


def _broadcast_partial_transcript(text: str):
    _broadcast({"type": "partial_transcript", "text": text})


def _broadcast_final_transcript(text: str):
    _broadcast({"type": "final_transcript", "text": text})


def _broadcast_response(text: str):
    _broadcast({"type": "response", "text": text})


def _broadcast_error(error: str):
    _broadcast({"type": "error", "error": error})


# ── Routes ───────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/command", methods=["POST"])
def handle_command():
    """Handle text commands (from the input box)."""
    try:
        data = request.json
        text = data.get("text", "")
        if not text:
            return jsonify({"success": False, "response": "Empty command", "action": ""})

        pipeline = _get_pipeline()

        # Process via the pipeline's command handler for consistency
        if pipeline.command_handler:
            result = pipeline.command_handler(text)
            # Also speak the response via TTS
            pipeline.tts.speak(result.get("response", ""))
            # Broadcast the response
            _broadcast_response(result.get("response", ""))
        else:
            kernel = _get_kernel()
            result = kernel.process_command(text)

        return jsonify(result)

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Flask API Error: {error_trace}")
        return jsonify({"success": False, "response": f"Internal Error: {str(e)}", "action": ""})


@app.route("/api/pipeline/start", methods=["POST"])
def pipeline_start():
    """Start the voice pipeline (always-on listening)."""
    try:
        pipeline = _get_pipeline()
        pipeline.start()
        return jsonify({"success": True, "status": "started"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/pipeline/stop", methods=["POST"])
def pipeline_stop():
    """Stop the voice pipeline."""
    try:
        pipeline = _get_pipeline()
        pipeline.stop()
        return jsonify({"success": True, "status": "stopped"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/pipeline/state", methods=["GET"])
def pipeline_state():
    """Get current pipeline state."""
    try:
        pipeline = _get_pipeline()
        return jsonify({
            "state": pipeline.state_name,
            "running": pipeline.is_running,
        })
    except Exception as e:
        return jsonify({"state": "unknown", "error": str(e)})


@app.route("/api/pipeline/interrupt", methods=["POST"])
def pipeline_interrupt():
    """Interrupt current operation (stop TTS, cancel listening)."""
    try:
        pipeline = _get_pipeline()
        pipeline.interrupt()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/performance", methods=["GET"])
def performance_report():
    """Get performance metrics."""
    try:
        _get_pipeline()  # Ensure initialized
        if _performance:
            return jsonify(_performance.get_report())
        return jsonify({})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/environment", methods=["GET"])
def environment_state():
    """Get current environment state."""
    try:
        _get_pipeline()  # Ensure initialized
        if _environment:
            return jsonify(_environment.state.to_dict())
        return jsonify({})
    except Exception as e:
        return jsonify({"error": str(e)})


# ── WebSocket endpoint ───────────────────────────────────────────

try:
    from flask_sock import Sock

    sock = Sock(app)

    @sock.route("/ws")
    def websocket_handler(ws):
        """
        Bidirectional WebSocket for real-time voice pipeline communication.

        Outgoing events (server → client):
          {"type": "state_change", "state": "ambient|listening|processing|speaking|follow_up"}
          {"type": "partial_transcript", "text": "..."}
          {"type": "final_transcript", "text": "..."}
          {"type": "response", "text": "..."}
          {"type": "error", "error": "..."}

        Incoming events (client → server):
          {"type": "text_command", "text": "..."}
          {"type": "interrupt"}
          {"type": "start_pipeline"}
          {"type": "stop_pipeline"}
        """
        with _ws_lock:
            _ws_clients.append(ws)

        logger.info("WebSocket client connected. Total: %d", len(_ws_clients))

        # Send current state
        try:
            pipeline = _get_pipeline()
            ws.send(json.dumps({
                "type": "state_change",
                "state": pipeline.state_name,
            }))
        except Exception:
            pass

        try:
            while True:
                msg = ws.receive()
                if msg is None:
                    break

                try:
                    data = json.loads(msg)
                    event_type = data.get("type", "")

                    if event_type == "text_command":
                        text = data.get("text", "").strip()
                        if text:
                            pipeline = _get_pipeline()
                            pipeline.process_text_command(text)

                    elif event_type == "interrupt":
                        pipeline = _get_pipeline()
                        pipeline.interrupt()

                    elif event_type == "start_pipeline":
                        pipeline = _get_pipeline()
                        pipeline.start()

                    elif event_type == "stop_pipeline":
                        pipeline = _get_pipeline()
                        pipeline.stop()

                except json.JSONDecodeError:
                    logger.warning("Invalid WebSocket message: %s", msg)
                except Exception as e:
                    logger.error("WebSocket message handling error: %s", e)

        except Exception:
            pass
        finally:
            with _ws_lock:
                if ws in _ws_clients:
                    _ws_clients.remove(ws)
            logger.info("WebSocket client disconnected. Remaining: %d", len(_ws_clients))

except ImportError:
    logger.warning("flask-sock not installed. WebSocket support disabled. Install with: pip install flask-sock")


# ── Legacy voice endpoints (kept for backward compatibility) ─────

@app.route("/api/voice/speak", methods=["POST"])
def voice_speak():
    """Speak text aloud via the new TTS engine."""
    try:
        data = request.json
        text = data.get("text", "")
        if text:
            pipeline = _get_pipeline()
            pipeline.tts.speak(text)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ── Server startup ───────────────────────────────────────────────

def start_server(port=5000):
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def start_server_in_thread(port=5000):
    thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    thread.start()
    return thread
