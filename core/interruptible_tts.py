"""
J.A.R.V.I.S. Interruptible Text-to-Speech
Neural TTS using edge-tts with pygame-based playback.
Can be interrupted instantly at any point during speech.
"""

import threading
import asyncio
import tempfile
import os
import time
import logging

logger = logging.getLogger("jarvis.tts")


class InterruptibleTTS:
    """
    High-quality interruptible text-to-speech.

    Uses Microsoft's edge-tts for neural voice synthesis and pygame.mixer
    for audio playback. Speech can be interrupted at any moment by calling
    interrupt().

    The key design: edge-tts generates the full audio file first (fast, ~200ms
    for short sentences), then pygame plays it. Interruption simply stops
    pygame playback immediately.

    For longer texts, sentences are split and played sequentially, allowing
    interruption between sentences with zero latency.
    """

    def __init__(
        self,
        voice: str = "en-US-GuyNeural",
        rate: str = "+10%",
        volume: str = "+0%",
    ):
        self.voice = voice
        self.rate = rate
        self.volume = volume

        # State
        self._speaking = False
        self._interrupted = False
        self._speak_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._current_text = ""
        self._spoken_text = ""       # Text that was actually spoken before interrupt

        # Pygame initialization
        self._pygame_initialized = False

        # Callbacks
        self.on_speaking_start: callable | None = None   # () -> None
        self.on_speaking_done: callable | None = None    # () -> None
        self.on_interrupted: callable | None = None      # (spoken_so_far: str) -> None
        self.on_error: callable | None = None            # (error: str) -> None

        # Temp file cleanup
        self._temp_files: list[str] = []

    # ── Public API ───────────────────────────────────────────────

    def speak(self, text: str):
        """
        Speak the given text. Non-blocking — runs in a background thread.
        If already speaking, interrupts current speech and starts new one.
        """
        if not text or not text.strip():
            return

        # If already speaking, interrupt first
        if self._speaking:
            self.interrupt()
            time.sleep(0.1)  # Brief pause for clean transition

        self._interrupted = False
        self._current_text = text.strip()
        self._spoken_text = ""

        self._speak_thread = threading.Thread(
            target=self._speak_worker, args=(text.strip(),), daemon=True, name="tts-speak"
        )
        self._speak_thread.start()

    def speak_stream(self, text_stream):
        """
        Speak from a generator yielding text chunks. Non-blocking.
        Accumulates chunks into sentences and plays them sequentially.
        """
        if self._speaking:
            self.interrupt()
            time.sleep(0.1)

        self._interrupted = False
        self._spoken_text = ""

        self._speak_thread = threading.Thread(
            target=self._speak_stream_worker, args=(text_stream,), daemon=True, name="tts-speak-stream"
        )
        self._speak_thread.start()

    def interrupt(self):
        """
        Immediately stop speaking. Thread-safe.
        Fires on_interrupted callback with the text spoken so far.
        """
        with self._lock:
            if not self._speaking:
                return
            self._interrupted = True

        # Stop pygame playback immediately
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

        logger.info("TTS interrupted. Spoken so far: '%s'", self._spoken_text)

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    # ── Internal ─────────────────────────────────────────────────

    def _init_pygame(self):
        """Initialize pygame mixer for audio playback."""
        if self._pygame_initialized:
            return

        try:
            import pygame
            pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=2048)
            self._pygame_initialized = True
            logger.info("pygame.mixer initialized for TTS playback.")
        except Exception as e:
            logger.error("Failed to initialize pygame.mixer: %s", e)
            if self.on_error:
                self.on_error(f"TTS audio init failed: {e}")
            raise

    def _speak_worker(self, text: str):
        """Background worker that synthesizes and plays speech."""
        try:
            self._init_pygame()

            with self._lock:
                self._speaking = True

            if self.on_speaking_start:
                self.on_speaking_start()

            # Split text into sentences for granular interruption
            sentences = self._split_sentences(text)

            for i, sentence in enumerate(sentences):
                if self._interrupted:
                    break

                if not sentence.strip():
                    continue

                # Synthesize sentence to temp file
                temp_path = self._synthesize(sentence)
                if not temp_path:
                    continue

                # Track what we're about to speak
                self._spoken_text += sentence + " "

                # Play the audio
                if not self._play_audio(temp_path):
                    break  # Interrupted during playback

                # Clean up temp file
                self._safe_delete(temp_path)

        except Exception as e:
            logger.error("TTS worker error: %s", e)
            if self.on_error:
                self.on_error(f"TTS error: {e}")
        finally:
            was_interrupted = self._interrupted
            with self._lock:
                self._speaking = False
                self._interrupted = False

            if was_interrupted and self.on_interrupted:
                self.on_interrupted(self._spoken_text.strip())
            elif self.on_speaking_done:
                self.on_speaking_done()

            # Clean up any remaining temp files
            self._cleanup_temp_files()

    def _speak_stream_worker(self, text_stream):
        """Background worker that synthesizes and plays streaming speech."""
        import re
        try:
            self._init_pygame()

            with self._lock:
                self._speaking = True

            if self.on_speaking_start:
                self.on_speaking_start()

            buffer = ""
            for chunk in text_stream:
                if self._interrupted:
                    break
                buffer += chunk
                
                # Check for sentence boundaries
                match = re.search(r'(?<=[.!?])\s+', buffer)
                if match:
                    sentence = buffer[:match.start()].strip()
                    buffer = buffer[match.end():]
                    
                    if not sentence:
                        continue
                        
                    temp_path = self._synthesize(sentence)
                    if not temp_path:
                        continue
                        
                    self._spoken_text += sentence + " "
                    if not self._play_audio(temp_path):
                        break
                    self._safe_delete(temp_path)
                    
            # Process remaining buffer
            if buffer.strip() and not self._interrupted:
                sentence = buffer.strip()
                temp_path = self._synthesize(sentence)
                if temp_path:
                    self._spoken_text += sentence + " "
                    self._play_audio(temp_path)
                    self._safe_delete(temp_path)

        except Exception as e:
            logger.error("TTS stream worker error: %s", e)
            if self.on_error:
                self.on_error(f"TTS stream error: {e}")
        finally:
            was_interrupted = self._interrupted
            with self._lock:
                self._speaking = False
                self._interrupted = False

            if was_interrupted and self.on_interrupted:
                self.on_interrupted(self._spoken_text.strip())
            elif self.on_speaking_done:
                self.on_speaking_done()

            self._cleanup_temp_files()

    def _synthesize(self, text: str) -> str | None:
        """
        Synthesize text to a temporary MP3 file using edge-tts.
        Returns the path to the temp file, or None on failure.
        """
        try:
            import edge_tts

            # Create temp file
            fd, temp_path = tempfile.mkstemp(suffix=".mp3", prefix="jarvis_tts_")
            os.close(fd)
            self._temp_files.append(temp_path)

            # Run the async edge-tts communicate
            async def _generate():
                communicate = edge_tts.Communicate(
                    text,
                    voice=self.voice,
                    rate=self.rate,
                    volume=self.volume,
                )
                await communicate.save(temp_path)

            # Run in a new event loop (we're in a thread)
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_generate())
            finally:
                loop.close()

            return temp_path

        except Exception as e:
            logger.error("TTS synthesis failed for '%s': %s", text[:50], e)
            return None

    def _play_audio(self, filepath: str) -> bool:
        """
        Play an audio file via pygame.mixer. Blocks until done or interrupted.
        Returns True if completed, False if interrupted.
        """
        try:
            import pygame

            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()

            # Wait for playback to finish, checking for interruption
            while pygame.mixer.music.get_busy():
                if self._interrupted:
                    pygame.mixer.music.stop()
                    return False
                time.sleep(0.05)  # 50ms poll — responsive enough for interruption

            return True

        except Exception as e:
            logger.error("Audio playback error: %s", e)
            return False

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """
        Split text into sentences for granular interruption.
        Keeps punctuation attached to the sentence.
        """
        import re

        # Split on sentence-ending punctuation followed by a space or end of string
        # But keep the punctuation with the sentence
        parts = re.split(r'(?<=[.!?])\s+', text)
        result = [p.strip() for p in parts if p.strip()]

        # If no sentence boundaries found, return the whole text as one chunk
        if not result:
            return [text]

        return result

    @staticmethod
    def _safe_delete(filepath: str):
        """Safely delete a temp file."""
        try:
            if os.path.exists(filepath):
                os.unlink(filepath)
        except Exception:
            pass

    def _cleanup_temp_files(self):
        """Clean up all tracked temp files."""
        for path in self._temp_files:
            self._safe_delete(path)
        self._temp_files.clear()

    def cleanup(self):
        """Clean up resources. Call on shutdown."""
        self.interrupt()
        self._cleanup_temp_files()
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.quit()
        except Exception:
            pass
