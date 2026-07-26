"""
J.A.R.V.I.S. Voice Engine
Handles speech recognition (STT) and text-to-speech (TTS).
Runs listening in a background thread to keep the UI responsive.
"""

import threading
import queue
import time

import speech_recognition as sr
import pyttsx3

from config import (
    VOICE_RATE, VOICE_VOLUME, VOICE_ID,
    LISTEN_TIMEOUT, PHRASE_TIME_LIMIT,
    ENERGY_THRESHOLD, DYNAMIC_ENERGY
)


class VoiceEngine:
    """
    Unified voice engine providing:
      - listen()  → captures microphone audio → returns text
      - speak()   → converts text → audible speech
      - Threaded continuous listening with callbacks
    """

    def __init__(self):
        # ── Speech Recognition Setup ─────────────────────────────
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = ENERGY_THRESHOLD
        self.recognizer.dynamic_energy_threshold = DYNAMIC_ENERGY
        self.microphone = sr.Microphone()

        # Calibrate to ambient noise on startup
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

        # ── TTS Setup ────────────────────────────────────────────
        self._tts_engine = pyttsx3.init("sapi5")
        voices = self._tts_engine.getProperty("voices")
        if VOICE_ID < len(voices):
            self._tts_engine.setProperty("voice", voices[VOICE_ID].id)
        self._tts_engine.setProperty("rate", VOICE_RATE)
        self._tts_engine.setProperty("volume", VOICE_VOLUME)

        # ── State ────────────────────────────────────────────────
        self._listening = False
        self._speaking = False
        self._listen_thread = None
        self._tts_lock = threading.Lock()
        self._mic_lock = threading.Lock()

        # ── Callbacks ────────────────────────────────────────────
        self.on_listening_start = None     # () → None
        self.on_listening_stop = None      # () → None
        self.on_recognized = None          # (text: str) → None
        self.on_error = None               # (error: str) → None
        self.on_speaking_start = None      # () → None
        self.on_speaking_done = None       # () → None

    # ─── Text-to-Speech ──────────────────────────────────────────

    def speak(self, text: str):
        """Speak the given text aloud. Thread-safe."""
        if not text:
            return

        def _do_speak():
            with self._tts_lock:
                self._speaking = True
                if self.on_speaking_start:
                    self.on_speaking_start()
                try:
                    # Re-init engine each call to avoid COM threading issues
                    engine = pyttsx3.init("sapi5")
                    voices = engine.getProperty("voices")
                    if VOICE_ID < len(voices):
                        engine.setProperty("voice", voices[VOICE_ID].id)
                    engine.setProperty("rate", VOICE_RATE)
                    engine.setProperty("volume", VOICE_VOLUME)
                    engine.say(text)
                    engine.runAndWait()
                    engine.stop()
                except Exception as e:
                    if self.on_error:
                        self.on_error(f"TTS Error: {e}")
                finally:
                    self._speaking = False
                    if self.on_speaking_done:
                        self.on_speaking_done()

        thread = threading.Thread(target=_do_speak, daemon=True)
        thread.start()

    # ─── Single Listen ───────────────────────────────────────────

    def listen_once(self) -> str | None:
        """
        Block and listen for a single phrase.
        Returns recognized text or None on failure.
        """
        # Prevent concurrent microphone access from multiple threads
        if not self._mic_lock.acquire(blocking=False):
            return None

        try:
            with self.microphone as source:
                audio = self.recognizer.listen(
                    source,
                    timeout=LISTEN_TIMEOUT,
                    phrase_time_limit=PHRASE_TIME_LIMIT
                )
            text = self.recognizer.recognize_google(audio)
            return text.lower().strip()
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            if self.on_error:
                self.on_error(f"Speech API error: {e}")
            return None
        except Exception as e:
            if self.on_error:
                self.on_error(f"Listen error: {e}")
            return None
        finally:
            self._mic_lock.release()

    # ─── Threaded Listening ──────────────────────────────────────

    def start_listening(self):
        """Start a background thread that listens for one command."""
        if self._listening:
            return

        self._listening = True

        def _listen_worker():
            if self.on_listening_start:
                self.on_listening_start()

            text = self.listen_once()

            self._listening = False
            if self.on_listening_stop:
                self.on_listening_stop()

            if text and self.on_recognized:
                self.on_recognized(text)
            # Silent return on timeout / no speech — don't spam errors

        self._listen_thread = threading.Thread(target=_listen_worker, daemon=True)
        self._listen_thread.start()

    def stop_listening(self):
        """Signal the listening loop to stop."""
        self._listening = False

    # ─── Properties ──────────────────────────────────────────────

    @property
    def is_listening(self) -> bool:
        return self._listening

    @property
    def is_speaking(self) -> bool:
        return self._speaking
