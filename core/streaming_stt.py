"""
J.A.R.V.I.S. Streaming Speech-to-Text
Real-time speech recognition using faster-whisper on CPU.
Provides both streaming partial results and final transcription.
Includes intelligent end-of-speech detection that distinguishes
thinking pauses from finished speaking.
"""

import threading
import time
import queue
import logging
import io
import wave
import tempfile
import os
import numpy as np

logger = logging.getLogger("jarvis.streaming_stt")


class StreamingSTT:
    """
    Streaming speech-to-text powered by faster-whisper (CTranslate2).

    Runs entirely on CPU to leave GPU free for the LLM.
    Accumulates audio chunks and periodically transcribes them,
    emitting partial results as the user speaks.

    Intelligent silence detection:
      - Tracks energy levels to detect speech vs silence
      - Uses adaptive thresholds: short pause (1.5s) vs long pause (3s)
      - Sentence completeness heuristic to decide if user is done
    """

    SAMPLE_RATE = 16_000
    CHANNELS = 1
    BYTES_PER_SAMPLE = 2   # int16

    def __init__(
        self,
        model_size: str = "base.en",
        device: str = "cpu",
        compute_type: str = "int8",
        silence_threshold_short: float = 1.5,
        silence_threshold_long: float = 3.0,
        energy_silence_db: float = -40.0,
        max_recording_seconds: float = 30.0,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.silence_threshold_short = silence_threshold_short
        self.silence_threshold_long = silence_threshold_long
        self.energy_silence_db = energy_silence_db
        self.max_recording_seconds = max_recording_seconds

        # State
        self._model = None
        self._recording = False
        self._audio_buffer = bytearray()
        self._audio_lock = threading.Lock()
        self._silence_start: float | None = None
        self._speech_detected = False
        self._last_transcript = ""
        self._record_thread: threading.Thread | None = None
        self._continuous = False
        self._current_energy_db = -100.0

        # Audio stream (shared or standalone)
        self._pyaudio_instance = None
        self._stream = None
        self._owns_stream = False

        # Callbacks
        self.on_partial_transcript: callable | None = None   # (text: str) -> None
        self.on_final_transcript: callable | None = None     # (text: str) -> None
        self.on_ambient_transcript: callable | None = None   # (text: str) -> None
        self.on_speech_start: callable | None = None         # () -> None
        self.on_speech_end: callable | None = None           # () -> None
        self.on_error: callable | None = None                # (error: str) -> None

    @property
    def current_energy_db(self) -> float:
        """Get the latest computed microphone energy level."""
        return self._current_energy_db

    # ── Model loading ────────────────────────────────────────────

    def load_model(self):
        """Pre-load the Whisper model. Called lazily on first use."""
        if self._model is not None:
            return

        try:
            from faster_whisper import WhisperModel
            logger.info(
                "Loading faster-whisper model: %s (device=%s, compute=%s)",
                self.model_size, self.device, self.compute_type,
            )
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info("faster-whisper model loaded successfully.")
        except Exception as e:
            logger.error("Failed to load faster-whisper model: %s", e)
            if self.on_error:
                self.on_error(f"STT model load failed: {e}")
            raise

    # ── Recording ────────────────────────────────────────────────

    def start_recording(self, continuous: bool = False):
        """
        Start capturing audio from the microphone.
        Runs in a background thread. Continuously feeds audio into the buffer
        and runs silence detection. When speech ends, transcribes it.
        If continuous=True, it doesn't stop recording, but emits transcripts and resets.
        """
        if self._recording:
            return

        self.load_model()
        self._recording = True
        self._continuous = continuous
        self._audio_buffer = bytearray()
        self._silence_start = None
        self._speech_detected = False
        self._last_transcript = ""

        self._record_thread = threading.Thread(
            target=self._record_loop, daemon=True, name="stt-record"
        )
        self._record_thread.start()
        logger.info("STT recording started.")

    def stop_recording(self) -> str:
        """
        Stop recording and return the final transcript.
        If there's buffered audio, transcribes it before returning.
        """
        self._recording = False
        if self._record_thread and self._record_thread.is_alive():
            self._record_thread.join(timeout=5.0)

        # Transcribe any remaining audio
        final_text = self._transcribe_buffer()
        self._cleanup_stream()

        if final_text and self.on_final_transcript:
            self.on_final_transcript(final_text)

        logger.info("STT recording stopped. Final: '%s'", final_text)
        return final_text

    def feed_audio(self, audio_chunk: bytes):
        """
        Feed raw audio data (int16, 16kHz, mono) from an external source.
        Used when the wake word detector's audio stream is shared.
        """
        with self._audio_lock:
            self._audio_buffer.extend(audio_chunk)

    @property
    def is_recording(self) -> bool:
        return self._recording

    # ── Internal recording loop ──────────────────────────────────

    def _record_loop(self):
        """Main recording loop: capture audio, detect silence, transcribe."""
        try:
            self._init_audio()
        except Exception as e:
            logger.error("Failed to initialize audio for STT: %s", e)
            self._recording = False
            return

        chunk_size = 1600  # 100ms at 16kHz
        partial_interval = 1.0  # Emit partial transcripts every 1s
        last_partial_time = time.time()
        record_start = time.time()

        while self._recording:
            try:
                raw_data = self._stream.read(chunk_size, exception_on_overflow=False)
                audio_np = np.frombuffer(raw_data, dtype=np.int16)

                with self._audio_lock:
                    self._audio_buffer.extend(raw_data)

                # ── Energy-based speech/silence detection ────────
                energy_db = self._compute_energy_db(audio_np)
                self._current_energy_db = energy_db
                
                # Record ambient noise for environment monitor
                from core.performance_monitor import get_performance_monitor
                get_performance_monitor().record_noise_level(energy_db)
                
                is_speech = energy_db > self.energy_silence_db

                if is_speech:
                    if not self._speech_detected:
                        self._speech_detected = True
                        logger.info("Speech detected (energy=%.1f dB)", energy_db)
                        if self.on_speech_start:
                            self.on_speech_start()
                    self._silence_start = None
                else:
                    if self._speech_detected and self._silence_start is None:
                        self._silence_start = time.time()

                # ── Partial transcription ────────────────────────
                now = time.time()
                if (
                    self._speech_detected
                    and now - last_partial_time >= partial_interval
                    and len(self._audio_buffer) > self.SAMPLE_RATE * self.BYTES_PER_SAMPLE  # >1s of audio
                ):
                    partial = self._transcribe_buffer(final=False)
                    if partial and partial != self._last_transcript:
                        self._last_transcript = partial
                        if self.on_partial_transcript:
                            self.on_partial_transcript(partial)
                    last_partial_time = now

                # ── End-of-speech detection ──────────────────────
                if self._speech_detected and self._silence_start is not None:
                    silence_duration = now - self._silence_start

                    # Adaptive threshold: use longer threshold if transcript
                    # looks like an incomplete thought
                    threshold = self._get_adaptive_silence_threshold()

                    if silence_duration >= threshold:
                        logger.info(
                            "End of speech detected (silence=%.1fs, threshold=%.1fs)",
                            silence_duration, threshold,
                        )
                        if self._continuous:
                            # In continuous mode, transcribe what we have, emit it, and clear buffer
                            final_text = self._transcribe_buffer(final=True)
                            if final_text and self.on_ambient_transcript:
                                self.on_ambient_transcript(final_text)
                            
                            # Reset for next utterance
                            with self._audio_lock:
                                self._audio_buffer.clear()
                            self._speech_detected = False
                            self._silence_start = None
                            self._last_transcript = ""
                        else:
                            self._recording = False
                            break

                # ── Max recording timeout ────────────────────────
                if now - record_start >= self.max_recording_seconds:
                    logger.warning("Max recording time reached (%.0fs)", self.max_recording_seconds)
                    self._recording = False
                    break

            except Exception as e:
                if self._recording:
                    logger.error("STT record loop error: %s", e)
                    time.sleep(0.1)

        # Final transcription
        final_text = self._transcribe_buffer(final=True)
        self._cleanup_stream()

        if self.on_speech_end:
            self.on_speech_end()

        if final_text and self.on_final_transcript:
            self.on_final_transcript(final_text)

    def _get_adaptive_silence_threshold(self) -> float:
        """
        Choose a silence threshold based on whether the current transcript
        looks like a complete thought or an unfinished one.
        """
        transcript = self._last_transcript.strip().lower()
        if not transcript:
            return self.silence_threshold_short

        # Indicators that the user might still be talking:
        incomplete_indicators = [
            transcript.endswith(" and"),
            transcript.endswith(" or"),
            transcript.endswith(" but"),
            transcript.endswith(" then"),
            transcript.endswith(" the"),
            transcript.endswith(" a"),
            transcript.endswith(" to"),
            transcript.endswith(" in"),
            transcript.endswith(" for"),
            transcript.endswith(" with"),
            transcript.endswith("..."),
            transcript.endswith(","),
        ]

        if any(incomplete_indicators):
            return self.silence_threshold_long

        return self.silence_threshold_short

    # ── Audio utilities ──────────────────────────────────────────

    def _init_audio(self):
        """Open a microphone stream for recording."""
        if self._stream is not None:
            return

        import pyaudio

        self._pyaudio_instance = pyaudio.PyAudio()
        self._stream = self._pyaudio_instance.open(
            format=pyaudio.paInt16,
            channels=self.CHANNELS,
            rate=self.SAMPLE_RATE,
            input=True,
            frames_per_buffer=1600,
        )
        self._owns_stream = True

    def _cleanup_stream(self):
        """Close the audio stream if we own it."""
        if not self._owns_stream:
            return

        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if self._pyaudio_instance is not None:
            try:
                self._pyaudio_instance.terminate()
            except Exception:
                pass
            self._pyaudio_instance = None

    @staticmethod
    def _compute_energy_db(audio: np.ndarray) -> float:
        """Compute the energy of an audio chunk in dB."""
        if len(audio) == 0:
            return -100.0
        rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
        if rms < 1e-10:
            return -100.0
        return 20 * np.log10(rms / 32768.0)

    # ── Transcription ────────────────────────────────────────────

    def _transcribe_buffer(self, final: bool = True) -> str:
        """
        Transcribe the current audio buffer.
        Uses Cloud STT (Google Free API) if online to save CPU.
        Otherwise falls back to local faster-whisper.
        """
        with self._audio_lock:
            if len(self._audio_buffer) < self.SAMPLE_RATE * self.BYTES_PER_SAMPLE * 0.3:
                return ""  # Less than 0.3s of audio — skip
            audio_data = bytes(self._audio_buffer)

        # Check for cloud availability
        try:
            from core.llm_provider import is_online
            use_cloud = is_online()
        except ImportError:
            use_cloud = False

        if use_cloud:
            # Skip partial transcripts when using cloud to avoid spamming the free API
            if not final:
                return ""
            
            try:
                import speech_recognition as sr
                recognizer = sr.Recognizer()
                
                # Convert raw bytes to standard WAV format in memory
                wav_io = io.BytesIO()
                with wave.open(wav_io, 'wb') as wf:
                    wf.setnchannels(self.CHANNELS)
                    wf.setsampwidth(self.BYTES_PER_SAMPLE)
                    wf.setframerate(self.SAMPLE_RATE)
                    wf.writeframes(audio_data)
                
                wav_io.seek(0)
                with sr.AudioFile(wav_io) as source:
                    audio = recognizer.record(source)
                
                logger.info("Using Cloud STT (recognize_google) for zero-CPU transcription...")
                result = recognizer.recognize_google(audio)
                return result.strip()
                
            except sr.UnknownValueError:
                return ""
            except sr.RequestError as e:
                logger.warning("Cloud STT failed (%s), falling back to local Whisper", e)
                # Fall through to local Whisper
            except Exception as e:
                logger.error("Cloud STT error: %s", e)
                # Fall through to local Whisper

        # Local fallback (faster-whisper)
        if self._model is None:
            return ""

        try:
            # Convert raw bytes to float32 array for faster-whisper
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            segments, info = self._model.transcribe(
                audio_np,
                beam_size=5 if final else 1,
                language="en",
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=200,
                ),
            )

            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            result = " ".join(text_parts).strip()
            return result

        except Exception as e:
            logger.error("Transcription error: %s", e)
            if self.on_error:
                self.on_error(f"Transcription failed: {e}")
            return ""
