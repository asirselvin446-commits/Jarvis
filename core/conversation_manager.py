"""
J.A.R.V.I.S. Conversation Manager
Maintains active conversation state for multi-turn understanding.
Handles context, corrections, cancellations, pronouns, and entity tracking.
"""

import re
import time
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("jarvis.conversation")


class ConversationTurn:
    """A single turn in the conversation."""

    def __init__(self, role: str, text: str, entities: dict | None = None):
        self.role = role          # "user" or "jarvis"
        self.text = text
        self.timestamp = time.time()
        self.entities = entities or {}

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "text": self.text,
            "timestamp": self.timestamp,
            "entities": self.entities,
        }


class ConversationManager:
    """
    Manages active conversation context for natural multi-turn interactions.

    Features:
      - Sliding window of recent conversation turns
      - Entity extraction and tracking (apps, files, URLs, names)
      - Correction detection ("I mean X", "no, do Y")
      - Cancellation detection ("cancel that", "never mind")
      - Pronoun resolution context for the LLM
      - Auto-expiration after configurable silence gap
    """

    # Correction patterns
    CORRECTION_PATTERNS = [
        re.compile(r"^(?:i mean|i meant)\s+(.+)", re.IGNORECASE),
        re.compile(r"^(?:no|nah),?\s*(?:i (?:mean|want|need)t?\s+)?(.+)", re.IGNORECASE),
        re.compile(r"^(?:actually|wait),?\s+(.+)", re.IGNORECASE),
        re.compile(r"^(?:sorry|oops),?\s*(?:i mean(?:t)?\s+)?(.+)", re.IGNORECASE),
        re.compile(r"^not\s+(?:that|this),?\s+(.+)", re.IGNORECASE),
        re.compile(r"^(?:instead|rather),?\s+(.+)", re.IGNORECASE),
    ]

    # Cancellation patterns
    CANCELLATION_PATTERNS = [
        re.compile(r"^(?:cancel|abort|stop|forget|skip)\s*(?:that|this|it)?\.?$", re.IGNORECASE),
        re.compile(r"^never\s*mind\.?$", re.IGNORECASE),
        re.compile(r"^(?:don'?t|do not)\s+(?:do|bother|worry)\s*(?:about)?\s*(?:that|it)?\.?$", re.IGNORECASE),
        re.compile(r"^(?:scratch|disregard)\s+(?:that|this|it)\.?$", re.IGNORECASE),
    ]

    # Simple entity extraction patterns
    ENTITY_PATTERNS = {
        "app": re.compile(
            r"(?:open|launch|start|close|switch to|run)\s+([\w\s]+?)(?:\s+and|\s*$|\.)",
            re.IGNORECASE,
        ),
        "url": re.compile(
            r"(https?://\S+|(?:www\.)\S+|[\w-]+\.(?:com|org|net|io|dev|app)\S*)",
            re.IGNORECASE,
        ),
        "query": re.compile(
            r"(?:search|google|look up|find)\s+(?:for\s+)?[\"']?(.+?)[\"']?(?:\s+on|\s*$|\.)",
            re.IGNORECASE,
        ),
        "file": re.compile(
            r"(?:open|create|delete|move|copy|rename)\s+(?:the\s+)?(?:file|folder|directory)\s+[\"']?(.+?)[\"']?(?:\s|$|\.)",
            re.IGNORECASE,
        ),
    }

    def __init__(
        self,
        max_turns: int = 10,
        conversation_timeout: float = 30.0,
    ):
        self.max_turns = max_turns
        self.conversation_timeout = conversation_timeout

        self.turns: list[ConversationTurn] = []
        self.active_entities: dict[str, str] = {}  # {"app": "Chrome", "query": "Python"}
        self.session_start: float | None = None
        self.last_activity: float = 0.0

        # Subscribe to proactive context updates
        try:
            from core.message_bus import get_message_bus
            bus = get_message_bus()
            bus.subscribe("context_update", self._on_context_update)
        except Exception:
            pass

    def _on_context_update(self, event_data: dict):
        """Update active entities from proactive environment context."""
        payload = event_data.get("payload", {})
        for key, value in payload.items():
            self.active_entities[key] = value

    # ── Public API ───────────────────────────────────────────────

    def add_user_turn(self, text: str) -> dict:
        """
        Add a user turn to the conversation.

        Returns a dict with:
          - "type": "command" | "correction" | "cancellation"
          - "text": the resolved text
          - "original": original input
          - "correction_target": what was corrected (if correction)
        """
        now = time.time()

        # Check if conversation expired
        if self.last_activity > 0 and (now - self.last_activity) > self.conversation_timeout:
            self.reset()

        if self.session_start is None:
            self.session_start = now
        self.last_activity = now

        # ── Check for cancellation ───────────────────────────────
        if self.detect_cancellation(text):
            logger.info("Cancellation detected: '%s'", text)
            self._add_turn("user", text)
            return {"type": "cancellation", "text": text, "original": text}

        # ── Check for correction ─────────────────────────────────
        correction = self.detect_correction(text)
        if correction:
            logger.info("Correction detected: '%s' → '%s'", text, correction)
            self._add_turn("user", text, {"correction": correction})
            return {
                "type": "correction",
                "text": correction,
                "original": text,
                "correction_target": self._get_last_user_command(),
            }

        # ── Normal command ───────────────────────────────────────
        entities = self._extract_entities(text)
        self.active_entities.update(entities)
        self._add_turn("user", text, entities)

        return {"type": "command", "text": text, "original": text}

    def add_assistant_turn(self, text: str):
        """Add an assistant response to the conversation."""
        self.last_activity = time.time()
        self._add_turn("jarvis", text)

    def get_context_for_llm(self) -> str:
        """
        Format conversation history for the LLM system prompt.
        Provides enough context for pronoun resolution and multi-turn understanding.
        """
        if not self.turns:
            return ""

        lines = ["Recent conversation (for context and pronoun resolution):"]
        for turn in self.turns[-self.max_turns:]:
            role_label = "User" if turn.role == "user" else "Jarvis"
            lines.append(f"  {role_label}: {turn.text}")

        if self.active_entities:
            lines.append("\nCurrently tracked entities:")
            for entity_type, entity_value in self.active_entities.items():
                lines.append(f"  - {entity_type}: {entity_value}")

        return "\n".join(lines)

    def detect_correction(self, text: str) -> str | None:
        """
        Check if the text is a correction like "I mean X" or "no, do Y".
        Returns the corrected text, or None if not a correction.
        """
        for pattern in self.CORRECTION_PATTERNS:
            match = pattern.match(text.strip())
            if match:
                return match.group(1).strip()
        return None

    def detect_cancellation(self, text: str) -> bool:
        """Check if the text is a cancellation like "cancel that" or "never mind"."""
        for pattern in self.CANCELLATION_PATTERNS:
            if pattern.match(text.strip()):
                return True
        return False

    def reset(self):
        """Reset the conversation state."""
        self.turns.clear()
        self.active_entities.clear()
        self.session_start = None
        self.last_activity = 0.0
        logger.info("Conversation context reset.")

    @property
    def is_active(self) -> bool:
        """Whether a conversation session is active."""
        if not self.session_start:
            return False
        return (time.time() - self.last_activity) < self.conversation_timeout

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    # ── Internal ─────────────────────────────────────────────────

    def _add_turn(self, role: str, text: str, entities: dict | None = None):
        """Add a turn to the history, trimming to max_turns."""
        turn = ConversationTurn(role=role, text=text, entities=entities)
        self.turns.append(turn)

        # Trim old turns
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

    def _extract_entities(self, text: str) -> dict:
        """Extract entities from user text."""
        entities = {}
        for entity_type, pattern in self.ENTITY_PATTERNS.items():
            match = pattern.search(text)
            if match:
                entities[entity_type] = match.group(1).strip()
        return entities

    def _get_last_user_command(self) -> str | None:
        """Get the text of the last user command."""
        for turn in reversed(self.turns):
            if turn.role == "user":
                return turn.text
        return None
