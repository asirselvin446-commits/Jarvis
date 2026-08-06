"""
Voice Orchestrator for Jarvis
Handles real-time voice conversation with interrupt handling,
streaming responses, and context management.
"""

import os
import logging
import threading
import queue
import time
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum
import json

logger = logging.getLogger(__name__)

# Voice configuration
DEFAULT_VOICE = "default"
SPEECH_TIMEOUT_SECONDS = 30
MIN_SPEECH_DURATION = 0.5  # seconds
MAX_SILENCE_DURATION = 2.0  # seconds


class ConversationState(Enum):
    """Voice conversation states."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


class VoiceOrchestrator:
    """
    Orchestrates real-time voice conversation:
    - Listens for voice input
    - Detects speech boundaries
    - Handles interrupts
    - Generates responses
    - Manages text-to-speech
    """
    
    def __init__(self):
        self.state = ConversationState.IDLE
        self.is_running = False
        
        # Conversation management
        self.conversation_history: List[Dict[str, str]] = []
        self.current_turn_start = None
        self.user_input_buffer = ""
        self.response_buffer = ""
        
        # Threading
        self.audio_queue = queue.Queue()
        self.response_queue = queue.Queue()
        self.interrupt_event = threading.Event()
        self.pause_event = threading.Event()
        
        # Configuration
        self.interrupt_enabled = True
        self.streaming_enabled = True
        self.context: Dict[str, Any] = {}
        
        # Callbacks
        self.on_input_complete = None
        self.on_response_start = None
        self.on_response_chunk = None
        self.on_response_complete = None
        self.on_interrupt = None
        self.on_error = None
        
        # Statistics
        self.total_turns = 0
        self.total_interrupts = 0
        self.avg_response_latency = 0.0
        self.start_time = datetime.now()
    
    def start(self):
        """Start the voice orchestrator."""
        if self.is_running:
            return
        
        self.is_running = True
        self.state = ConversationState.LISTENING
        logger.info("Voice orchestrator started")
    
    def stop(self):
        """Stop the voice orchestrator."""
        self.is_running = False
        self.state = ConversationState.IDLE
        logger.info("Voice orchestrator stopped")
    
    def process_audio_input(self, audio_chunk: Any, transcript: str) -> bool:
        """
        Process audio input from microphone.
        
        Args:
            audio_chunk: Raw audio data
            transcript: Transcribed text
            
        Returns:
            True if input was processed successfully
        """
        if not self.is_running:
            return False
        
        if self.state == ConversationState.SPEAKING:
            # User interrupted
            if self.interrupt_enabled:
                self._handle_interrupt()
            return False
        
        if self.state == ConversationState.LISTENING:
            # Accumulate input
            self.user_input_buffer += " " + transcript
            self.current_turn_start = datetime.now()
            return True
        
        return False
    
    def input_complete(self) -> bool:
        """
        Signal that user input is complete.
        Triggers processing and response generation.
        """
        if not self.user_input_buffer.strip():
            return False
        
        self.state = ConversationState.PROCESSING
        
        # Log input
        self.conversation_history.append({
            "role": "user",
            "content": self.user_input_buffer.strip(),
            "timestamp": datetime.now().isoformat(),
        })
        
        return True
    
    def generate_response(
        self,
        llm_response: str,
        streaming: bool = True,
    ):
        """
        Generate voice response from LLM output.
        
        Args:
            llm_response: Response text from LLM
            streaming: Whether to stream chunks
        """
        if not self.is_running:
            return
        
        self.state = ConversationState.SPEAKING
        self.response_buffer = llm_response
        
        # Log response
        self.conversation_history.append({
            "role": "assistant",
            "content": llm_response,
            "timestamp": datetime.now().isoformat(),
        })
        
        # Trigger callback
        if self.on_response_start:
            self.on_response_start()
        
        if streaming:
            self._stream_response(llm_response)
        else:
            self._speak_response(llm_response)
        
        # Return to listening
        self.state = ConversationState.LISTENING
        self.total_turns += 1
        
        # Trigger callback
        if self.on_response_complete:
            self.on_response_complete()
    
    def _stream_response(self, text: str):
        """Stream response in chunks."""
        # Split into sentences
        sentences = text.split(".")
        
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            # Check for interrupt
            if self.interrupt_event.is_set():
                self.interrupt_event.clear()
                break
            
            # Wait if paused
            while self.pause_event.is_set():
                time.sleep(0.1)
            
            chunk = sentence.strip() + "."
            
            # Trigger callback for chunk
            if self.on_response_chunk:
                self.on_response_chunk(chunk)
            
            # Put in response queue
            self.response_queue.put({
                "chunk": chunk,
                "timestamp": datetime.now().isoformat(),
            })
            
            # Simulate speech time
            # Assume ~150 words per minute = ~2.5 words per second
            time.sleep(len(chunk.split()) / 2.5)
    
    def _speak_response(self, text: str):
        """Speak response without streaming."""
        # In production, this would use TTS
        logger.info(f"Speaking: {text[:100]}...")
        self.response_queue.put({
            "text": text,
            "timestamp": datetime.now().isoformat(),
        })
    
    def _handle_interrupt(self):
        """Handle user interrupt."""
        self.total_interrupts += 1
        self.state = ConversationState.LISTENING
        self.response_buffer = ""
        
        logger.info("User interrupt detected")
        
        if self.on_interrupt:
            self.on_interrupt()
    
    def interrupt(self):
        """Trigger interrupt (user is speaking)."""
        self.interrupt_event.set()
    
    def pause(self):
        """Pause voice output."""
        self.pause_event.set()
    
    def resume(self):
        """Resume voice output."""
        self.pause_event.clear()
    
    def clear_input(self):
        """Clear accumulated input."""
        self.user_input_buffer = ""
        self.current_turn_start = None
    
    def get_conversation_history(self, max_turns: int = None) -> List[Dict]:
        """Get conversation history."""
        history = self.conversation_history
        if max_turns:
            history = history[-max_turns:]
        return history
    
    def set_context(self, context: Dict[str, Any]):
        """Update conversation context."""
        self.context.update(context)
    
    def get_context(self) -> Dict[str, Any]:
        """Get current context."""
        return self.context.copy()
    
    def set_voice_config(
        self,
        voice: str = None,
        speed: float = None,
        pitch: float = None,
    ):
        """Configure voice output."""
        if voice:
            self.context["voice"] = voice
        if speed is not None:
            self.context["speech_speed"] = speed
        if pitch is not None:
            self.context["speech_pitch"] = pitch
    
    def get_state(self) -> str:
        """Get current state."""
        return self.state.value
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get conversation statistics."""
        uptime = (datetime.now() - self.start_time).total_seconds() / 60
        
        return {
            "state": self.state.value,
            "is_running": self.is_running,
            "total_turns": self.total_turns,
            "total_interrupts": self.total_interrupts,
            "interrupt_rate": round(
                (self.total_interrupts / self.total_turns * 100)
                if self.total_turns > 0 else 0,
                2
            ),
            "uptime_minutes": round(uptime, 2),
            "context_vars": len(self.context),
            "history_turns": len(self.conversation_history),
        }
    
    def export_conversation(self) -> Dict[str, Any]:
        """Export conversation data."""
        return {
            "timestamp": datetime.now().isoformat(),
            "statistics": self.get_statistics(),
            "history": self.get_conversation_history(),
            "context": self.get_context(),
        }


class RealTimeInterruptHandler:
    """
    Handles real-time interrupt detection and processing.
    Monitors for user speech while Jarvis is speaking.
    """
    
    def __init__(self, voice_orchestrator: VoiceOrchestrator):
        self.orchestrator = voice_orchestrator
        self.is_monitoring = False
        self.monitor_thread = None
    
    def start_monitoring(self):
        """Start interrupt monitoring."""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_for_interrupts)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop interrupt monitoring."""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
    
    def _monitor_for_interrupts(self):
        """Monitor audio stream for user speech."""
        while self.is_monitoring:
            # Check if we're speaking
            if self.orchestrator.state == ConversationState.SPEAKING:
                # Listen for user voice
                # In production, this would check actual audio input
                if self._detect_user_speech():
                    self.orchestrator.interrupt()
            
            time.sleep(0.1)
    
    def _detect_user_speech(self) -> bool:
        """Detect if user is speaking."""
        # Placeholder: In production, would check audio stream
        return False


class ContextManager:
    """
    Manages conversation context and state.
    Enables context-aware responses.
    """
    
    def __init__(self):
        self.global_context: Dict[str, Any] = {}
        self.session_context: Dict[str, Any] = {}
        self.user_preferences: Dict[str, Any] = {}
    
    def set_global_context(self, key: str, value: Any):
        """Set global context variable."""
        self.global_context[key] = value
    
    def set_session_context(self, key: str, value: Any):
        """Set session context variable."""
        self.session_context[key] = value
    
    def set_user_preference(self, key: str, value: Any):
        """Set user preference."""
        self.user_preferences[key] = value
    
    def get_full_context(self) -> Dict[str, Any]:
        """Get all context combined."""
        return {
            "global": self.global_context,
            "session": self.session_context,
            "user": self.user_preferences,
        }
    
    def to_prompt_context(self) -> str:
        """Convert context to prompt text."""
        lines = []
        
        if self.user_preferences:
            lines.append("User Preferences:")
            for k, v in self.user_preferences.items():
                lines.append(f"  - {k}: {v}")
        
        if self.session_context:
            lines.append("\nSession Context:")
            for k, v in self.session_context.items():
                lines.append(f"  - {k}: {v}")
        
        return "\n".join(lines)


# Global instances
_orchestrator = None
_interrupt_handler = None
_context_manager = None


def get_voice_orchestrator() -> VoiceOrchestrator:
    """Get or create global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = VoiceOrchestrator()
    return _orchestrator


def get_interrupt_handler() -> RealTimeInterruptHandler:
    """Get or create global interrupt handler."""
    global _interrupt_handler, _orchestrator
    if _interrupt_handler is None:
        _orchestrator = get_voice_orchestrator()
        _interrupt_handler = RealTimeInterruptHandler(_orchestrator)
    return _interrupt_handler


def get_context_manager() -> ContextManager:
    """Get or create global context manager."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
