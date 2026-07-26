"""
J.A.R.V.I.S. Command Log
Chat-style scrollable log showing user commands and Jarvis responses.
"""

import tkinter as tk
import customtkinter as ctk
import datetime

from ui.theme import (
    BG_DARK, BG_MEDIUM, BG_LIGHT, BG_INPUT,
    ACCENT_CYAN, ACCENT_GREEN, ACCENT_PURPLE, STATUS_ERROR, ACCENT_AMBER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM, TEXT_ACCENT,
    BORDER_SUBTLE,
    FONT_FAMILY, FONT_BODY_SIZE, FONT_SMALL_SIZE, FONT_TINY_SIZE,
)


class CommandLog(ctk.CTkFrame):
    """
    Scrollable chat-style command log.
    Shows user commands, Jarvis responses, and system actions.
    """

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("fg_color", BG_DARK)
        kwargs.setdefault("corner_radius", 12)
        super().__init__(parent, **kwargs)

        # Header
        self._header = ctk.CTkFrame(self, fg_color="transparent", height=36)
        self._header.pack(fill="x", padx=16, pady=(12, 0))
        self._header.pack_propagate(False)

        ctk.CTkLabel(
            self._header,
            text="💬  Command Log",
            font=(FONT_FAMILY, FONT_BODY_SIZE, "bold"),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).pack(side="left")

        self._clear_btn = ctk.CTkButton(
            self._header,
            text="Clear",
            width=50, height=24,
            font=(FONT_FAMILY, FONT_TINY_SIZE),
            fg_color=BG_MEDIUM,
            hover_color=BG_LIGHT,
            text_color=TEXT_DIM,
            corner_radius=6,
            command=self.clear,
        )
        self._clear_btn.pack(side="right")

        # Scrollable log area
        self._scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=BG_DARK,
            scrollbar_button_color=BG_MEDIUM,
            scrollbar_button_hover_color=BG_LIGHT,
            corner_radius=0,
        )
        self._scroll_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        self._entries = []

    # ─── Public API ──────────────────────────────────────────────

    def add_user_message(self, text: str):
        """Add a user voice command entry."""
        self._add_entry("user", f"🎤  {text}", ACCENT_CYAN)

    def add_jarvis_response(self, text: str):
        """Add a Jarvis response entry."""
        self._add_entry("jarvis", f"🤖  {text}", TEXT_PRIMARY)

    def add_system_action(self, text: str):
        """Add a system action entry (dimmed)."""
        self._add_entry("system", f"⚡  {text}", TEXT_DIM)

    def add_error(self, text: str):
        """Add an error entry."""
        self._add_entry("error", f"❌  {text}", STATUS_ERROR)

    def clear(self):
        """Clear all log entries."""
        for entry in self._entries:
            entry.destroy()
        self._entries.clear()

    # ─── Internal ────────────────────────────────────────────────

    def _add_entry(self, entry_type: str, text: str, color: str):
        """Create a styled log entry."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        # Container for the entry
        entry_frame = ctk.CTkFrame(
            self._scroll_frame,
            fg_color="transparent",
            corner_radius=0,
        )
        entry_frame.pack(fill="x", padx=4, pady=2)

        # Timestamp
        ctk.CTkLabel(
            entry_frame,
            text=timestamp,
            font=(FONT_FAMILY, FONT_TINY_SIZE),
            text_color=TEXT_DIM,
            anchor="w",
            width=60,
        ).pack(side="left", padx=(4, 8))

        # Message type indicator bar
        bar_colors = {
            "user": ACCENT_CYAN,
            "jarvis": ACCENT_GREEN,
            "system": ACCENT_PURPLE,
            "error": STATUS_ERROR,
        }

        bar = ctk.CTkFrame(
            entry_frame,
            fg_color=bar_colors.get(entry_type, TEXT_DIM),
            width=3,
            height=18,
            corner_radius=2,
        )
        bar.pack(side="left", padx=(0, 8))

        # Message text
        msg_label = ctk.CTkLabel(
            entry_frame,
            text=text,
            font=(FONT_FAMILY, FONT_SMALL_SIZE),
            text_color=color,
            anchor="w",
            wraplength=500,
            justify="left",
        )
        msg_label.pack(side="left", fill="x", expand=True)

        self._entries.append(entry_frame)

        # Auto-scroll to bottom
        self._scroll_frame.after(50, lambda: self._scroll_frame._parent_canvas.yview_moveto(1.0))
