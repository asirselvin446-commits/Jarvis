"""
J.A.R.V.I.S. Message Bus
Simple in-memory message bus for inter-agent communication.
Agents can publish events and subscribe to topics so they share context
(e.g., "I opened Chrome" → web agent knows Chrome is ready).
"""

import threading
from datetime import datetime
from typing import Callable, Dict, List, Any, Optional
from collections import deque


class Message:
    """A single message on the bus."""

    def __init__(self, topic: str, sender: str, payload: Any):
        self.topic = topic
        self.sender = sender
        self.payload = payload
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "sender": self.sender,
            "payload": self.payload,
            "timestamp": self.timestamp
        }

    def __repr__(self):
        return f"<Message topic='{self.topic}' sender='{self.sender}'>"


class MessageBus:
    """
    In-memory publish/subscribe message bus for agent communication.
    
    Agents can:
      - publish(topic, payload) to broadcast events
      - subscribe(topic, callback) to listen for events
      - get_recent(topic, n) to retrieve recent messages on a topic
    """

    def __init__(self, max_history: int = 100):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._history: Dict[str, deque] = {}
        self._lock = threading.Lock()
        self._max_history = max_history

    def publish(self, topic: str, sender: str, payload: Any):
        """
        Publish a message to a topic. All subscribers get notified.
        Also stores the message in history for late-joining agents.
        """
        msg = Message(topic, sender, payload)

        with self._lock:
            # Store in history
            if topic not in self._history:
                self._history[topic] = deque(maxlen=self._max_history)
            self._history[topic].append(msg)

            # Notify subscribers (copy list to avoid mutation during iteration)
            callbacks = list(self._subscribers.get(topic, []))
            # Also notify wildcard subscribers
            callbacks += list(self._subscribers.get("*", []))

        for callback in callbacks:
            try:
                callback(msg)
            except Exception as e:
                print(f"[MessageBus] Callback error for topic '{topic}': {e}")

    def subscribe(self, topic: str, callback: Callable):
        """
        Subscribe to a topic. Callback receives a Message object.
        Use topic='*' to subscribe to ALL messages.
        """
        with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Callable):
        """Remove a callback from a topic."""
        with self._lock:
            if topic in self._subscribers:
                self._subscribers[topic] = [
                    cb for cb in self._subscribers[topic] if cb != callback
                ]

    def get_recent(self, topic: str, n: int = 5) -> List[dict]:
        """Get the N most recent messages on a topic."""
        with self._lock:
            if topic not in self._history:
                return []
            messages = list(self._history[topic])[-n:]
            return [m.to_dict() for m in messages]

    def get_context_summary(self) -> str:
        """
        Get a text summary of recent bus activity for agent context.
        Used by the orchestrator to give agents awareness of what happened.
        """
        with self._lock:
            lines = []
            for topic, msgs in self._history.items():
                recent = list(msgs)[-3:]  # Last 3 per topic
                for m in recent:
                    lines.append(f"[{m.sender}] {m.topic}: {m.payload}")
            return "\n".join(lines[-10:]) if lines else ""

    def clear(self):
        """Clear all history and subscribers."""
        with self._lock:
            self._subscribers.clear()
            self._history.clear()


# Global singleton message bus instance
_bus_instance: Optional[MessageBus] = None
_bus_lock = threading.Lock()


def get_message_bus() -> MessageBus:
    """Get or create the global message bus singleton."""
    global _bus_instance
    if _bus_instance is None:
        with _bus_lock:
            if _bus_instance is None:
                _bus_instance = MessageBus()
    return _bus_instance
