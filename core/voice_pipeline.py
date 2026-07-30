"""
J.A.R.V.I.S. Voice Pipeline
Central state machine managing the entire voice interaction lifecycle.

States:
  AMBIENT        → Wake word detector running, near-zero CPU
  LISTENING      → Capturing speech with streaming STT
  PROCESSING     → User's utterance complete, sent to orchestrator
  SPEAKING       → TTS playing response, listening for interruption
  FOLLOW_UP      → Waiting for follow-up command (no wake word needed)

The pipeline coordinates wake_word, streaming_stt, interruptible_tts,
and the orchestrator into a seamless, ambient voice experience.
"""

import enum
import threading
import time
import logging
import queue
from typing import Optional

from core.streaming_stt import StreamingSTT
from core.interruptible_tts import InterruptibleTTS

logger = logging.getLogger("jarvis.pipeline")


class PipelineState(enum.Enum):
    """Voice pipeline states."""
    IDLE = "idle"                 # Not started
    AMBIENT = "ambient"          # Wake word listening (ultra-low power)
    LISTENING = "listening"      # Actively capturing speech
    PROCESSING = "processing"    # Transcription done, executing command
    SPEAKING = "speaking"        # TTS playing response
    FOLLOW_UP = "follow_up"     # Waiting for follow-up (no wake word needed)


class VoicePipeline:
    """
    The central voice state machine.

    Orchestrates wake word detection, speech recognition, command processing,
    and text-to-speech into a natural, ambient voice experience.

    The user never presses a button. They just speak.
    """

    def __init__(
        self,
        stt_model: str = "base.en",
        stt_device: str = "cpu",
        tts_voice: str = "en-US-GuyNeural",
        tts_rate: str = "+10%",
        follow_up_window: float = 8.0,
        conversation_timeout: float = 30.0,
    ):
        # ── Configuration ────────────────────────────────────────
        self.follow_up_window = follow_up_window
        self.conversation_timeout = conversation_timeout

        # ── State ────────────────────────────────────────────────
        self._state = PipelineState.IDLE
        self._state_lock = threading.Lock()
        self._running = False
        self._follow_up_timer: threading.Timer | None = None
        self._conversation_active = False
        self._last_activity_time: float = 0.0

        # ── Components ───────────────────────────────────────────
        self._last_activity_time: float = 0.0
        self._interruption_thread: threading.Thread | None = None

        self.stt = StreamingSTT(
            model_size=stt_model,
            device=stt_device,
        )

        self.tts = InterruptibleTTS(
            voice=tts_voice,
            rate=tts_rate,
        )

        # ── Event queue for thread-safe state transitions ────────
        self._event_queue: queue.Queue = queue.Queue()
        self._event_thread: threading.Thread | None = None

        # ── Callbacks (UI/WebSocket notifications) ───────────────
        self.on_state_change: callable | None = None         # (state: str) -> None
        self.on_partial_transcript: callable | None = None   # (text: str) -> None
        self.on_final_transcript: callable | None = None     # (text: str) -> None
        self.on_response: callable | None = None             # (text: str) -> None
        self.on_error: callable | None = None                # (error: str) -> None

        # ── Command handler (set by web_server or main) ──────────
        self.command_handler: callable | None = None         # (text: str) -> dict

        # ── Wire up internal callbacks ───────────────────────────
        self._wire_callbacks()

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self):
        """Start the voice pipeline. Enters AMBIENT state."""
        if self._running:
            return

        self._running = True

        # Start event processing thread
        self._event_thread = threading.Thread(
            target=self._event_loop, daemon=True, name="pipeline-events"
        )
        self._event_thread.start()

        # Pre-load STT model in background (takes ~2-3s)
        threading.Thread(
            target=self._preload_stt, daemon=True, name="stt-preload"
        ).start()

        # Start ambient STT listening (VAD-triggered wake word)
        self.stt.start_recording(continuous=True)
        self._set_state(PipelineState.AMBIENT)

        logger.info("Voice pipeline started. State: AMBIENT")

        if not getattr(self, "_has_greeted", False):
            self._has_greeted = True
            def _boot_greeting():
                import datetime
                hour = datetime.datetime.now().hour
                if hour < 12:
                    greeting = "Good morning, sir. Systems are online."
                elif hour < 18:
                    greeting = "Good afternoon, sir. Systems are online."
                else:
                    greeting = "Good evening, sir. Systems are online."
                
                if self.on_response:
                    self.on_response(greeting)
                
                self._set_state(PipelineState.SPEAKING)
                self.tts.speak(greeting)
            
            threading.Thread(target=_boot_greeting, daemon=True, name="boot-greeting").start()

    def stop(self):
        """Shut down the voice pipeline and release all resources."""
        self._running = False
        self._cancel_follow_up_timer()

        if self.stt.is_recording:
            self.stt.stop_recording()
        self.tts.interrupt()
        self.tts.cleanup()

        self._set_state(PipelineState.IDLE)
        logger.info("Voice pipeline stopped.")

    @property
    def state(self) -> PipelineState:
        with self._state_lock:
            return self._state

    @property
    def state_name(self) -> str:
        return self.state.value

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Manual command input (from text box) ─────────────────────

    def process_text_command(self, text: str):
        """Process a typed command (from the text input box)."""
        if not text or not text.strip():
            return
        self._event_queue.put(("text_command", text.strip()))

    # ── Manual interrupt ─────────────────────────────────────────

    def interrupt(self):
        """Manually interrupt whatever is happening (stop TTS, cancel processing)."""
        self._event_queue.put(("interrupt", None))

    # ── State management ─────────────────────────────────────────

    def _set_state(self, new_state: PipelineState):
        """Thread-safe state transition with callback notification."""
        with self._state_lock:
            old_state = self._state
            self._state = new_state

        if old_state != new_state:
            logger.info("State: %s -> %s", old_state.value, new_state.value)
            if self.on_state_change:
                try:
                    self.on_state_change(new_state.value)
                except Exception as e:
                    logger.error("State change callback error: %s", e)

    # ── Internal callback wiring ─────────────────────────────────

    def _wire_callbacks(self):
        """Connect component callbacks to pipeline event handlers."""

        # Wake word detected → transition to LISTENING
        def _on_ambient_transcript(text):
            text_lower = text.lower()
            if self.state == PipelineState.AMBIENT and "jarvis" in text_lower:
                logger.info("Wake word 'jarvis' heard in ambient audio.")
                self._event_queue.put(("wake_word", None))
            elif self.state == PipelineState.FOLLOW_UP and text.strip():
                # In follow-up, any speech triggers
                logger.info("Speech heard in follow-up: %s", text)
                self._event_queue.put(("speech_final", text))
            elif self.state == PipelineState.SPEAKING and "jarvis" in text_lower:
                # User interrupted by saying wake word
                logger.info("Wake word heard during TTS — interrupting.")
                self._event_queue.put(("interrupt", None))
                self._event_queue.put(("wake_word", None))

        self.stt.on_ambient_transcript = _on_ambient_transcript

        # STT callbacks
        def _on_partial(text):
            if self.on_partial_transcript:
                self.on_partial_transcript(text)

        def _on_final(text):
            self._event_queue.put(("speech_final", text))

        def _on_speech_start():
            logger.info("Speech activity detected by STT.")

        def _on_speech_end():
            logger.info("Speech ended (silence detected by STT).")

        self.stt.on_partial_transcript = _on_partial
        self.stt.on_final_transcript = _on_final
        self.stt.on_speech_start = _on_speech_start
        self.stt.on_speech_end = _on_speech_end
        self.stt.on_error = lambda e: self._event_queue.put(("error", e))

        # TTS callbacks
        def _on_speaking_start():
            # Start STT in continuous mode if not already running, so it can catch wake word interruptions
            if not self.stt.is_recording:
                self.stt.start_recording(continuous=True)

        def _on_speaking_done():
            self._event_queue.put(("tts_done", None))

        def _on_tts_interrupted(spoken_so_far):
            self._event_queue.put(("tts_interrupted", spoken_so_far))

        self.tts.on_speaking_start = _on_speaking_start
        self.tts.on_speaking_done = _on_speaking_done
        self.tts.on_interrupted = _on_tts_interrupted
        self.tts.on_error = lambda e: self._event_queue.put(("error", e))

    # Event loop (single-threaded state transitions) ───────────

    def _event_loop(self):
        """
        Process events from the queue. All state transitions happen here
        to avoid race conditions. This is the pipeline's "brain."
        """
        while self._running:
            try:
                event_type, payload = self._event_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                current_state = self.state

                if event_type == "wake_word":
                    self._handle_wake_word(current_state)

                elif event_type == "speech_final":
                    self._handle_speech_final(payload, current_state)

                elif event_type == "text_command":
                    self._handle_text_command(payload, current_state)

                elif event_type == "tts_done":
                    self._handle_tts_done(current_state)

                elif event_type == "tts_interrupted":
                    self._handle_tts_interrupted(payload, current_state)

                elif event_type == "follow_up_timeout":
                    self._handle_follow_up_timeout(current_state)

                elif event_type == "interrupt":
                    self._handle_interrupt(current_state)

                elif event_type == "error":
                    logger.error("Pipeline error event: %s", payload)
                    if self.on_error:
                        self.on_error(str(payload))

                else:
                    logger.warning("Unknown event type: %s", event_type)

            except Exception as e:
                logger.error("Event handling error (%s): %s", event_type, e)

    # ── Event handlers ───────────────────────────────────────────

    def _handle_wake_word(self, current_state: PipelineState):
        """Handle wake word detection."""
        if current_state == PipelineState.SPEAKING:
            # User is interrupting TTS — stop speaking and start listening
            logger.info("Wake word during SPEAKING — interrupting TTS.")
            self.tts.interrupt()
            self._start_listening()

        elif current_state in (PipelineState.AMBIENT, PipelineState.FOLLOW_UP):
            # Normal activation
            logger.info("Wake word detected — activating.")
            self._cancel_follow_up_timer()
            self._start_listening()

        elif current_state == PipelineState.LISTENING:
            # Already listening — ignore
            logger.debug("Wake word while already LISTENING — ignoring.")

        elif current_state == PipelineState.PROCESSING:
            # Currently processing a command — queue for after
            logger.debug("Wake word during PROCESSING — ignoring.")

    def _handle_speech_final(self, text: str, current_state: PipelineState):
        """Handle final transcription from STT."""
        if current_state not in (PipelineState.LISTENING, PipelineState.FOLLOW_UP):
            logger.debug("Got speech_final in state %s — ignoring.", current_state.value)
            return

        cleaned_text = text.lower().strip().replace(".", "").replace(",", "").replace("!", "").replace("?", "")
        is_empty = not text or not text.strip() or cleaned_text in ("jarvis", "hey jarvis")

        if is_empty:
            if current_state == PipelineState.LISTENING:
                logger.info("Empty or wake-word-only transcript — acknowledging wake word.")
                def _say_yes():
                    ack = "Yes, sir?"
                    if self.on_response:
                        self.on_response(ack)
                    self._set_state(PipelineState.SPEAKING)
                    self.tts.speak(ack)
                threading.Thread(target=_say_yes, daemon=True, name="ack-response").start()
            return

        logger.info("Final transcript: '%s'", text)
        if self.on_final_transcript:
            self.on_final_transcript(text)

        self._process_command(text)

    def _handle_text_command(self, text: str, current_state: PipelineState):
        """Handle a typed text command."""
        # Stop anything currently happening
        if current_state == PipelineState.LISTENING:
            self.stt.stop_recording()
        elif current_state == PipelineState.SPEAKING:
            self.tts.interrupt()

        self._cancel_follow_up_timer()
        self._process_command(text)

    def _handle_tts_done(self, current_state: PipelineState):
        """Handle TTS finishing naturally."""
        if current_state != PipelineState.SPEAKING:
            return

        # Enter follow-up window — user can speak without wake word
        self._set_state(PipelineState.FOLLOW_UP)
        self._conversation_active = True
        self._last_activity_time = time.time()

        # Start follow-up timer
        self._start_follow_up_timer()

        # Start STT to catch follow-up without wake word
        if self.stt.is_recording:
            self.stt.stop_recording()
        self.stt.start_recording(continuous=True)

    def _handle_tts_interrupted(self, spoken_so_far: str, current_state: PipelineState):
        """Handle TTS being interrupted by user."""
        logger.info("TTS interrupted. Spoken: '%s'", spoken_so_far)
        # The wake_word handler will have already started listening

    def _handle_follow_up_timeout(self, current_state: PipelineState):
        """Handle follow-up window expiring."""
        if current_state == PipelineState.FOLLOW_UP:
            logger.info("Follow-up window expired — returning to ambient.")
            self._return_to_ambient()

    def _handle_interrupt(self, current_state: PipelineState):
        """Handle manual interrupt request."""
        if current_state == PipelineState.SPEAKING:
            self.tts.interrupt()
        elif current_state == PipelineState.LISTENING:
            self.stt.stop_recording()
        elif current_state == PipelineState.PROCESSING:
            pass  # Can't easily cancel LLM processing

        self._return_to_ambient()

    # ── Actions ──────────────────────────────────────────────────

    def _start_listening(self):
        """Transition to LISTENING state and start STT recording."""
        self._cancel_follow_up_timer()

        self._set_state(PipelineState.LISTENING)
        self._last_activity_time = time.time()
        
        # Play wake sound immediately for instant feedback
        try:
            import pygame
            import os
            wake_sound_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "wake.wav"))
            if os.path.exists(wake_sound_path):
                # Using pygame mixer which is already initialized by TTS
                pygame.mixer.Sound(wake_sound_path).play()
        except Exception as e:
            logger.error("Failed to play wake sound: %s", e)

        # Restart STT in final-capture mode
        if self.stt.is_recording:
            self.stt.stop_recording()
        self.stt.start_recording(continuous=False)

        # No passive listening method needed anymore; we just use STT continuous mode
        pass

    def _process_command(self, text: str):
        """Process a voice/text command through the orchestrator."""
        self._set_state(PipelineState.PROCESSING)
        self._last_activity_time = time.time()
        
        if self.stt.is_recording:
            self.stt.stop_recording()

        def _do_process():
            try:
                if self.command_handler:
                    result = self.command_handler(text)
                    response = result.get("response", "Done.")
                    response_stream = result.get("response_stream")
                else:
                    response = "No command handler configured."
                    response_stream = None

                if response_stream:
                    self._set_state(PipelineState.SPEAKING)
                    full_response = []
                    
                    def stream_wrapper():
                        for chunk in response_stream:
                            full_response.append(chunk)
                            yield chunk
                        
                        final_text = "".join(full_response)
                        if self.on_response:
                            self.on_response(final_text)
                            
                    self.tts.speak_stream(stream_wrapper())
                else:
                    if self.on_response:
                        self.on_response(response)

                    # Speak the response
                    self._set_state(PipelineState.SPEAKING)
                    self.tts.speak(response)

            except Exception as e:
                logger.error("Command processing error: %s", e)
                error_msg = f"Sorry, I encountered an error: {e}"
                if self.on_error:
                    self.on_error(str(e))
                if self.on_response:
                    self.on_response(error_msg)

                self._set_state(PipelineState.SPEAKING)
                self.tts.speak("Sorry, I encountered an error processing that command.")

        threading.Thread(target=_do_process, daemon=True, name="cmd-process").start()

    def _return_to_ambient(self):
        """Return to ambient wake word listening."""
        self._cancel_follow_up_timer()

        # Restart STT in continuous ambient mode
        if self.stt.is_recording:
            self.stt.stop_recording()
            
        self._conversation_active = False
        self._set_state(PipelineState.AMBIENT)
        self.stt.start_recording(continuous=True)

    def _start_follow_up_timer(self):
        """Start a timer that returns to ambient after follow_up_window seconds."""
        self._cancel_follow_up_timer()

        def _timeout():
            self._event_queue.put(("follow_up_timeout", None))

        self._follow_up_timer = threading.Timer(self.follow_up_window, _timeout)
        self._follow_up_timer.daemon = True
        self._follow_up_timer.start()

    def _cancel_follow_up_timer(self):
        """Cancel the follow-up timer if active."""
        if self._follow_up_timer is not None:
            self._follow_up_timer.cancel()
            self._follow_up_timer = None

    def _preload_stt(self):
        """Pre-load the STT model in the background so first use is instant."""
        try:
            self.stt.load_model()
            logger.info("STT model pre-loaded successfully.")
        except Exception as e:
            logger.error("STT pre-load failed: %s", e)
