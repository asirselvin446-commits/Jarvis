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
import webrtcvad

logger = logging.getLogger("jarvis.streaming_stt")

# Phrases Whisper commonly hallucinates on silence / background noise.
# These are dropped from transcripts so Jarvis never acts on imaginary speech.
_WHISPER_HALLUCINATIONS = {
    "thank you", "thank you.", "thanks for watching", "thanks for watching!",
    "thank you for watching", "thank you for watching.", "please subscribe",
    "subscribe", "you", "you.", ".", "..", "...", "bye", "bye.", "okay",
    "thank you very much", "thanks", "thanks.", "the", "so", "yeah",
    "i'm sorry", "i'm sorry.", "thank you so much", "please subscribe to my channel",
    "thank you for watching!", "♪", "[music]", "(music)", "[silence]",
    "peace", "peace.", "amen", "amen.", "oh", "oh.", "hmm", "mm", "mmm",
}

# Vocabulary hint fed to Whisper to bias decoding toward assistant commands and
# proper nouns it would otherwise mishear. This measurably improves accuracy on
# the words that matter most for a voice assistant.
_STT_INITIAL_PROMPT = (
    "Jarvis, open, close, launch, play, pause, search, Google, YouTube, Spotify, "
    "Chrome, volume, brightness, screenshot, email, WhatsApp, remind me, schedule, "
    "shut down, restart, terminal, PowerShell, file, folder, code, commit."
)


def _clean_transcript(text: str) -> str:
    """Drop Whisper hallucinations and junk; return '' if nothing meaningful remains."""
    if not text:
        return ""
    stripped = text.strip()
    if not stripped:
        return ""
    # Normalize for comparison: lowercase, collapse whitespace.
    normalized = " ".join(stripped.lower().split())
    if normalized in _WHISPER_HALLUCINATIONS:
        logger.debug("[STT] Dropped hallucinated transcript: %r", stripped)
        return ""
    # No letters or digits at all (e.g. "....", "♪♪") — pure punctuation/noise.
    if not any(c.isalnum() for c in normalized):
        logger.debug("[STT] Dropped non-alphanumeric transcript: %r", stripped)
        return ""
    # A single repeated token ("you you you", ".....") is almost always noise.
    tokens = normalized.replace(".", "").split()
    if tokens and len(set(tokens)) == 1 and len(tokens) >= 3:
        logger.debug("[STT] Dropped repeated-token noise: %r", stripped)
        return ""
    return stripped


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
        energy_silence_db: float = -30.0,
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
        self._vad = webrtcvad.Vad(3) # Aggressiveness 3 (highest) for filtering noise
        self._last_transcript = ""
        self._record_thread: threading.Thread | None = None
        self._running_thread = False
        self._continuous = False
        self._cumulative_speech_time: float = 0.0  # Total time above energy threshold
        self._last_speech_time: float | None = None  # Last chunk timestamp above threshold
        self._current_energy_db = -100.0
        self._model_lock = threading.Lock()

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

        # Prevent race condition when multiple threads call load_model() simultaneously
        with self._model_lock:
            if self._model is not None:
                return  # Another thread loaded it while we waited
            
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
        self._continuous = continuous
        with self._audio_lock:
            self._audio_buffer = bytearray()
        self._silence_start = None
        self._speech_detected = False
        self._last_transcript = ""

        if self._record_thread is None or not self._record_thread.is_alive():
            self._running_thread = True
            self._record_thread = threading.Thread(
                target=self._record_loop, daemon=True, name="stt-record"
            )
            self._record_thread.start()
            
        self._recording = True
        logger.info("STT recording started (continuous=%s).", continuous)

    def stop_recording(self) -> str:
        """
        Stop recording and return the final transcript.
        Leaves the background thread and audio stream running.
        """
        self._recording = False
        # Transcribe any remaining audio
        final_text = self._transcribe_buffer()
        # Do not cleanup stream here so it can be reused.

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

        while self._running_thread:
            if not self._recording:
                # Read and discard to prevent buffer overflow and stale data
                try:
                    self._stream.read(chunk_size, exception_on_overflow=False)
                except Exception:
                    pass
                time.sleep(0.01)
                # Reset timers while paused
                last_partial_time = time.time()
                record_start = time.time()
                continue

            try:
                raw_data = self._stream.read(chunk_size, exception_on_overflow=False)
                audio_np = np.frombuffer(raw_data, dtype=np.int16)

                with self._audio_lock:
                    self._audio_buffer.extend(raw_data)

                # ── Energy-based & WebRTC speech/silence detection ────────
                now = time.time()
                energy_db = self._compute_energy_db(audio_np)
                self._current_energy_db = energy_db
                
                # Record ambient noise for environment monitor
                from core.performance_monitor import get_performance_monitor
                get_performance_monitor().record_noise_level(energy_db)
                
                # Use WebRTC VAD for speech detection (much more accurate than raw energy)
                # WebRTC VAD requires exactly 10ms, 20ms, or 30ms frames.
                # chunk_size is 1600 (100ms). We split into three 30ms frames (480 samples each).
                is_speech = False
                try:
                    for i in range(3):
                        frame = raw_data[i*960:(i+1)*960]
                        if len(frame) == 960 and self._vad.is_speech(frame, self.SAMPLE_RATE):
                            is_speech = True
                            break
                except Exception:
                    # Fallback to energy if VAD fails
                    is_speech = energy_db > self.energy_silence_db

                if is_speech:
                    # Track cumulative time above speech threshold
                    chunk_duration = chunk_size / (self.SAMPLE_RATE * self.BYTES_PER_SAMPLE)  # ~0.1s
                    self._cumulative_speech_time += chunk_duration
                    self._last_speech_time = now
                    
                    # Only mark speech_detected after 0.2s of cumulative speech (lowered from 0.3s due to VAD accuracy)
                    if not self._speech_detected and self._cumulative_speech_time >= 0.2:
                        self._speech_detected = True
                        logger.info("Speech detected (energy=%.1f dB, cumulative=%.1fs)", energy_db, self._cumulative_speech_time)
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
                            # Skip if speech was too short (< 0.5s) — likely noise
                            speech_duration = now - record_start
                            if speech_duration >= 0.5:
                                final_text = self._transcribe_buffer(final=True)
                                if final_text and self.on_ambient_transcript:
                                    self.on_ambient_transcript(final_text)
                            
                            # Reset for next utterance
                            with self._audio_lock:
                                self._audio_buffer.clear()
                            self._speech_detected = False
                            self._silence_start = None
                            self._last_transcript = ""
                            self._cumulative_speech_time = 0.0
                            self._last_speech_time = None
                            record_start = time.time()  # Reset timer for next utterance
                        else:
                            self._recording = False
                            final_text = self._transcribe_buffer(final=True)
                            
                            if self.on_speech_end:
                                self.on_speech_end()
                                
                            if final_text and self.on_final_transcript:
                                self.on_final_transcript(final_text)
                                
                            with self._audio_lock:
                                self._audio_buffer.clear()
                            self._speech_detected = False
                            self._silence_start = None
                            self._last_transcript = ""
                # ── Max recording timeout ────────────────────────
                if now - record_start >= self.max_recording_seconds:
                    
                    if self._continuous:
                        # Only transcribe if there was genuine speech (not just ambient noise)
                        if self._speech_detected and self._cumulative_speech_time >= 0.5:
                            logger.warning("Max recording time reached (%.0fs) with %.1fs speech", self.max_recording_seconds, self._cumulative_speech_time)
                            final_text = self._transcribe_buffer(final=True)
                            if final_text and self.on_ambient_transcript:
                                self.on_ambient_transcript(final_text)
                        else:
                            logger.debug("Max recording timeout — no real speech detected (cumulative=%.1fs), skipping transcription", self._cumulative_speech_time)
                        
                        with self._audio_lock:
                            self._audio_buffer.clear()
                        self._speech_detected = False
                        self._silence_start = None
                        self._last_transcript = ""
                        self._cumulative_speech_time = 0.0
                        self._last_speech_time = None
                        record_start = time.time()
                    else:
                        self._recording = False
                        
                        final_text = self._transcribe_buffer(final=True)
                        if self.on_speech_end:
                            self.on_speech_end()
                        if final_text and self.on_final_transcript:
                            self.on_final_transcript(final_text)
                            
                        with self._audio_lock:
                            self._audio_buffer.clear()
                        self._speech_detected = False
                        self._silence_start = None
                        self._last_transcript = ""

            except Exception as e:
                if self._recording:
                    logger.error("STT record loop error: %s", e)
                    time.sleep(0.1)

        # When thread exits completely
        self._cleanup_stream()

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
        """Open a microphone stream for recording, supporting system default and fallback microphones."""
        if self._stream is not None:
            return

        import pyaudio

        self._pyaudio_instance = pyaudio.PyAudio()

        # 1. Try system default input device
        try:
            self._stream = self._pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=self.CHANNELS,
                rate=self.SAMPLE_RATE,
                input=True,
                frames_per_buffer=1600,
            )
            self._owns_stream = True
            logger.info("Initialized default system microphone stream.")
            return
        except Exception as e:
            logger.warning("Could not open default microphone: %s. Searching for available audio input devices...", e)

        # 2. Iterate through all available audio input devices (headsets, headphones, USB mics, etc.)
        try:
            info = self._pyaudio_instance.get_host_api_info_by_index(0)
            numdevices = info.get('deviceCount', 0)
            for i in range(0, numdevices):
                device_info = self._pyaudio_instance.get_device_info_by_host_api_device_index(0, i)
                if device_info.get('maxInputChannels', 0) > 0:
                    dev_name = device_info.get('name', f'Device {i}')
                    try:
                        self._stream = self._pyaudio_instance.open(
                            format=pyaudio.paInt16,
                            channels=self.CHANNELS,
                            rate=self.SAMPLE_RATE,
                            input=True,
                            input_device_index=i,
                            frames_per_buffer=1600,
                        )
                        self._owns_stream = True
                        logger.info("Initialized fallback microphone stream: '%s' (index %d)", dev_name, i)
                        return
                    except Exception as ex:
                        logger.debug("Failed to open microphone index %d (%s): %s", i, dev_name, ex)
        except Exception as e:
            logger.error("Audio device discovery error: %s", e)

        raise RuntimeError("No working microphone (headset, default, USB, or system input) could be initialized.")

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
    def _collect_confident_segments(segments) -> list:
        """Keep only segments the model is reasonably confident are real speech.

        faster-whisper exposes ``no_speech_prob`` and ``avg_logprob`` per segment;
        dropping high-no-speech / very-low-logprob segments removes most of the
        phantom text Whisper produces on silence and noise.
        """
        kept = []
        for seg in segments:
            no_speech = getattr(seg, "no_speech_prob", 0.0) or 0.0
            avg_logprob = getattr(seg, "avg_logprob", 0.0) or 0.0
            if no_speech > 0.85:
                logger.debug("[STT] Skipping segment (no_speech_prob=%.2f): %r",
                             no_speech, seg.text)
                continue
            if avg_logprob < -1.2:
                logger.debug("[STT] Skipping low-confidence segment (avg_logprob=%.2f): %r",
                             avg_logprob, seg.text)
                continue
            kept.append(seg.text.strip())
        return kept

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
                return _clean_transcript(result)
                
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

            # Decoding params tuned for command accuracy and low hallucination:
            #  - initial_prompt biases toward the assistant's vocabulary
            #  - condition_on_previous_text=False stops runaway repetition loops
            #  - no_speech/log_prob thresholds drop low-confidence garbage
            #  - temperature=0 makes decoding deterministic
            decode_kwargs = dict(
                beam_size=5 if final else 1,
                language="en",
                temperature=0.0,
                initial_prompt=_STT_INITIAL_PROMPT,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                log_prob_threshold=-1.0,
            )
            try:
                segments, info = self._model.transcribe(
                    audio_np,
                    vad_filter=True,
                    vad_parameters=dict(
                        min_silence_duration_ms=500,
                        speech_pad_ms=200,
                    ),
                    **decode_kwargs,
                )
                text_parts = self._collect_confident_segments(segments)
            except Exception as vad_err:
                logger.warning("vad_filter transcription error (%s), retrying with vad_filter=False", vad_err)
                segments, info = self._model.transcribe(
                    audio_np, vad_filter=False, **decode_kwargs,
                )
                text_parts = self._collect_confident_segments(segments)

            result = " ".join(text_parts).strip()
            return _clean_transcript(result)

        except Exception as e:
            logger.error("Transcription error: %s", e)
            if self.on_error:
                self.on_error(f"Transcription failed: {e}")
            return ""

