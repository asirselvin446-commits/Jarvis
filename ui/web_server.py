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

from flask import Flask, render_template, request, jsonify, Response

from core.security import RateLimiter

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

# ── Security: Request body size limit (10KB) ────────────────────
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024  # 10KB

# ── Security: Rate limiter for API endpoints ─────────────────────
_api_rate_limiter = RateLimiter(max_requests=30, window_seconds=60)


@app.after_request
def _add_security_headers(response: Response):
    """Add security headers and disable aggressive WebView caching."""
    # CORS: Only allow same-origin requests
    response.headers['Access-Control-Allow-Origin'] = 'http://127.0.0.1:5000'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    # Prevent MIME sniffing & clickjacking
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    # Prevent WebView2 / browser caching of dynamic templates and assets
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

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
            tts_volume=config.TTS_VOLUME,
            follow_up_window=config.FOLLOW_UP_WINDOW,
            conversation_timeout=config.CONVERSATION_TIMEOUT,
            energy_silence_db=config.ENERGY_SILENCE_DB,
            vad_aggressiveness=getattr(config, "VAD_AGGRESSIVENESS", 1),
            gain_enabled=getattr(config, "MIC_GAIN_ENABLED", True),
            gain_target_peak=getattr(config, "MIC_GAIN_TARGET_PEAK", 0.95),
            gain_max=getattr(config, "MIC_GAIN_MAX", 12.0),
            gain_noise_floor=getattr(config, "MIC_GAIN_NOISE_FLOOR", 200),
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

            # Process through the kernel unified pipeline with conversation context
            kernel = _get_kernel()
            result = kernel.process_command(text, conversation_context=context)

            # Record the response
            _conversation.add_assistant_turn(result.get("response", "Done."))

            _performance.stop_timer("processing_latency")
            _performance.stop_timer("total_response")

            return result

        _pipeline.command_handler = _handle_command

        # Start the environment monitor
        _environment.start()

        # Subscribe to Message Bus to broadcast agent activity to UI
        from core.message_bus import get_message_bus
        bus = get_message_bus()
        def _on_bus_event(msg):
            safe_payload = {}
            for k, v in msg.payload.items():
                if isinstance(v, (str, int, float, bool, type(None))):
                    safe_payload[k] = v
                elif isinstance(v, (dict, list)):
                    safe_payload[k] = str(v)
                else:
                    safe_payload[k] = str(v)
            _broadcast({
                "type": "bus_event",
                "topic": msg.topic,
                "sender": msg.sender,
                "payload": safe_payload
            })
        bus.subscribe("*", _on_bus_event)

        # Telemetry loop: sends CPU, RAM, LLM provider, and skills stats every 3s
        def _telemetry_loop():
            import psutil
            from core.llm_provider import get_provider_name, is_online
            from core.skills.skill_manager import get_skill_manager
            while True:
                time.sleep(3)
                try:
                    cpu = psutil.cpu_percent(interval=None)
                    ram = psutil.virtual_memory().percent
                    provider = get_provider_name()
                    online = is_online()
                    skills_cnt = len(get_skill_manager().skills)
                    _broadcast({
                        "type": "system_telemetry",
                        "cpu": cpu,
                        "ram": ram,
                        "provider": provider,
                        "online": online,
                        "active_skills": skills_cnt
                    })
                except Exception as e:
                    logger.debug("Telemetry error: %s", e)

        threading.Thread(target=_telemetry_loop, daemon=True, name="system-telemetry").start()

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
        # Rate limiting
        if not _api_rate_limiter.allow():
            return jsonify({"success": False, "response": "Rate limit exceeded. Try again later.", "action": ""}), 429

        data = request.json
        text = data.get("text", "") if data else ""
        if not text or not text.strip():
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


@app.route("/api/emergency_stop", methods=["POST"])
def emergency_stop():
    """Engage the emergency stop: halt any running agentic task + stop TTS."""
    try:
        from core.control import get_control_plane
        get_control_plane().request_stop("ui button")
        # Also interrupt any in-progress speech so it stops talking immediately.
        try:
            _get_pipeline().interrupt()
        except Exception:
            pass
        _broadcast({"type": "bus_event", "topic": "emergency_stop",
                    "sender": "ui", "payload": {"status": "stopped"}})
        return jsonify({"success": True, "status": "stopped"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/audit", methods=["GET"])
def audit_log():
    """Return the most recent audited tool executions (secrets redacted)."""
    try:
        from core.control import get_control_plane
        n = int(request.args.get("n", 20))
        return jsonify({"success": True, "records": get_control_plane().tail_audit(n)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


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

@app.route("/api/desktop", methods=["GET"])
def desktop_state():
    """Get current desktop context."""
    try:
        from core.desktop_monitor import get_desktop_monitor
        dm = get_desktop_monitor()
        return jsonify({
            "app": dm.current_app_exe,
            "title": dm.current_app_title,
            "context": dm.get_current_context()
        })
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


# ── Tactical, Dev, and Automation endpoints for Stark Mark VIII HUD ─────

@app.route("/api/tactical/intel", methods=["GET"])
def tactical_intel():
    """Get live world news and financial feeds."""
    try:
        from plugins.tactical_intelligence import get_world_news, get_world_finance_news
        news = get_world_news("general", limit=3)
        finance = get_world_finance_news()
        return jsonify({
            "success": True,
            "news": news,
            "finance": finance
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/automation/pipelines", methods=["GET"])
def list_pipelines():
    """List available master automation presets."""
    try:
        from core.automation_engine import get_automation_engine
        engine = get_automation_engine()
        return jsonify({"success": True, "presets": engine.list_presets()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/automation/run", methods=["POST"])
def run_pipeline():
    """Trigger a master automation pipeline preset."""
    try:
        data = request.json or {}
        preset_id = data.get("preset_id", "")
        if not preset_id:
            return jsonify({"success": False, "error": "No preset_id provided"})
        
        from core.automation_engine import get_automation_engine
        engine = get_automation_engine()
        result = engine.run_preset(preset_id)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/dev/context", methods=["GET"])
def dev_context():
    """Get project git status and Bolt dev environment details."""
    try:
        from plugins.coworker_tools import inspect_project_context
        from plugins.bolt_dev_engine import bolt_inspect_app
        ctx = inspect_project_context()
        bolt = bolt_inspect_app("jarvisautoapp")
        return jsonify({
            "success": True,
            "context": ctx,
            "bolt_app": bolt
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/status", methods=["GET"])
def system_status():
    """Get full system telemetry including GPU, RAM, MCP, and active tools."""
    try:
        import psutil
        from core.tool_manager import ToolManager
        tm = ToolManager()
        tools_count = len(tm.tools)
        
        gpu_info = "RTX 4050 6GB"
        try:
            import subprocess
            res = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,temperature.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().split(",")
                gpu_info = f"{parts[0].strip()} ({parts[1].strip()}MB / {parts[2].strip()}°C)"
        except Exception:
            pass

        return jsonify({
            "success": True,
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": psutil.virtual_memory().percent,
            "gpu": gpu_info,
            "tools_count": tools_count,
            "mcp_port": 8000,
            "status": "ONLINE"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ── Server startup ───────────────────────────────────────────────

def start_server(port=5000):
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def start_server_in_thread(port=5000):
    thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    thread.start()
    return thread
