"""
J.A.R.V.I.S. Main Application Window
Stunning dark-themed UI with animated waveform, mic control, and command log.
"""

import customtkinter as ctk
import tkinter as tk
import threading
import sys

from ui.theme import (
    BG_DARKEST, BG_DARK, BG_MEDIUM, BG_LIGHT, BG_INPUT,
    ACCENT_CYAN, ACCENT_PURPLE, ACCENT_GREEN, STATUS_ERROR, ACCENT_AMBER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM, TEXT_ACCENT,
    BORDER_SUBTLE, BORDER_ACTIVE,
    STATUS_IDLE, STATUS_LISTENING, STATUS_PROCESSING, STATUS_SPEAKING, STATUS_ERROR,
    FONT_FAMILY, FONT_TITLE_SIZE, FONT_HEADING_SIZE, FONT_BODY_SIZE, FONT_SMALL_SIZE, FONT_TINY_SIZE,
    MIC_BUTTON_SIZE,
)
from ui.waveform import WaveformVisualizer
from ui.command_log import CommandLog
from core.voice_engine import VoiceEngine
from core.os_kernel import OSKernel
from config import WINDOW_TITLE, WINDOW_SIZE, MIN_WIDTH, MIN_HEIGHT, ASSISTANT_NAME


# Configure CustomTkinter
ctk.set_appearance_mode("dark")


class JarvisApp(ctk.CTk):
    """Main J.A.R.V.I.S. application window."""

    def __init__(self):
        super().__init__()

        # ── Window Setup ─────────────────────────────────────────
        self.title(WINDOW_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.configure(fg_color=BG_DARKEST)

        # Try to set icon
        try:
            self.iconbitmap("assets/jarvis_icon.ico")
        except Exception:
            pass

        # ── Initialize Core ──────────────────────────────────────
        self.voice_engine = VoiceEngine()
        self.os_kernel = OSKernel()
        self._is_listening = False

        # Wire up voice engine callbacks
        self.voice_engine.on_listening_start = self._on_listening_start
        self.voice_engine.on_listening_stop = self._on_listening_stop
        self.voice_engine.on_recognized = self._on_recognized
        self.voice_engine.on_error = self._on_error
        self.voice_engine.on_speaking_start = self._on_speaking_start
        self.voice_engine.on_speaking_done = self._on_speaking_done

        # ── Build UI ─────────────────────────────────────────────
        self._build_header()
        self._build_waveform_section()
        self._build_control_bar()
        self._build_command_log()
        self._build_text_input()
        self._build_status_bar()

        # ── Startup greeting ─────────────────────────────────────
        self.after(500, self._startup_greeting)

        # Handle close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ═════════════════════════════════════════════════════════════
    # UI CONSTRUCTION
    # ═════════════════════════════════════════════════════════════

    def _build_header(self):
        """Build the top header with title and status."""
        header = ctk.CTkFrame(self, fg_color=BG_DARK, height=60, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        # Left: Logo area
        logo_frame = ctk.CTkFrame(header, fg_color="transparent")
        logo_frame.pack(side="left", padx=20, pady=10)

        # Glowing dot
        self._status_dot = ctk.CTkLabel(
            logo_frame,
            text="●",
            font=(FONT_FAMILY, 18),
            text_color=ACCENT_CYAN,
            width=20,
        )
        self._status_dot.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            logo_frame,
            text="J.A.R.V.I.S.",
            font=(FONT_FAMILY, FONT_TITLE_SIZE, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkLabel(
            logo_frame,
            text="  Voice Assistant",
            font=(FONT_FAMILY, FONT_SMALL_SIZE),
            text_color=TEXT_DIM,
        ).pack(side="left", padx=(4, 0), pady=(6, 0))

        # Right: Status text
        self._status_label = ctk.CTkLabel(
            header,
            text="● Online",
            font=(FONT_FAMILY, FONT_SMALL_SIZE),
            text_color=ACCENT_GREEN,
        )
        self._status_label.pack(side="right", padx=20)

    def _build_waveform_section(self):
        """Build the central waveform visualization area."""
        wave_container = ctk.CTkFrame(
            self,
            fg_color=BG_DARKEST,
            corner_radius=0,
        )
        wave_container.pack(fill="x", padx=20, pady=(10, 0))

        self.waveform = WaveformVisualizer(
            wave_container,
            bg=BG_DARKEST,
            height=160,
        )
        self.waveform.pack(fill="x", expand=True)

    def _build_control_bar(self):
        """Build the mic button and control bar."""
        control_frame = ctk.CTkFrame(
            self,
            fg_color="transparent",
            height=100,
        )
        control_frame.pack(fill="x", padx=20, pady=(0, 5))
        control_frame.pack_propagate(False)

        # Center container for mic button
        center = ctk.CTkFrame(control_frame, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Outer glow ring
        self._mic_outer = ctk.CTkFrame(
            center,
            fg_color=BG_MEDIUM,
            width=MIC_BUTTON_SIZE + 16,
            height=MIC_BUTTON_SIZE + 16,
            corner_radius=(MIC_BUTTON_SIZE + 16) // 2,
        )
        self._mic_outer.pack()
        self._mic_outer.pack_propagate(False)

        # Mic button
        self._mic_btn = ctk.CTkButton(
            self._mic_outer,
            text="🎤",
            width=MIC_BUTTON_SIZE,
            height=MIC_BUTTON_SIZE,
            corner_radius=MIC_BUTTON_SIZE // 2,
            fg_color=BG_LIGHT,
            hover_color=ACCENT_CYAN,
            text_color=TEXT_PRIMARY,
            font=(FONT_FAMILY, 24),
            command=self._toggle_listen,
        )
        self._mic_btn.place(relx=0.5, rely=0.5, anchor="center")

        # Instruction text below
        self._instruction_label = ctk.CTkLabel(
            control_frame,
            text="Click the mic or press Space to speak",
            font=(FONT_FAMILY, FONT_TINY_SIZE),
            text_color=TEXT_DIM,
        )
        self._instruction_label.place(relx=0.5, rely=0.92, anchor="center")

        # Bind spacebar
        self.bind("<space>", lambda e: self._toggle_listen())

    def _build_command_log(self):
        """Build the scrollable command history log."""
        self.command_log = CommandLog(self)
        self.command_log.pack(fill="both", expand=True, padx=20, pady=(5, 5))

    def _build_text_input(self):
        """Build the text input field for typing commands."""
        input_frame = ctk.CTkFrame(self, fg_color=BG_DARK, height=50, corner_radius=12)
        input_frame.pack(fill="x", padx=20, pady=(0, 5))
        input_frame.pack_propagate(False)

        self._text_input = ctk.CTkEntry(
            input_frame,
            placeholder_text="Type a command...",
            fg_color=BG_INPUT,
            border_color=BORDER_SUBTLE,
            border_width=1,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_DIM,
            font=(FONT_FAMILY, FONT_BODY_SIZE),
            corner_radius=8,
            height=36,
        )
        self._text_input.pack(side="left", fill="x", expand=True, padx=(12, 8), pady=7)
        self._text_input.bind("<Return>", self._on_text_submit)

        self._send_btn = ctk.CTkButton(
            input_frame,
            text="Send",
            width=60,
            height=36,
            fg_color=ACCENT_CYAN,
            hover_color=ACCENT_PURPLE,
            text_color=BG_DARKEST,
            font=(FONT_FAMILY, FONT_SMALL_SIZE, "bold"),
            corner_radius=8,
            command=self._on_text_submit,
        )
        self._send_btn.pack(side="right", padx=(0, 12), pady=7)

    def _build_status_bar(self):
        """Build the bottom status bar."""
        status_bar = ctk.CTkFrame(self, fg_color=BG_DARK, height=28, corner_radius=0)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)

        self._footer_label = ctk.CTkLabel(
            status_bar,
            text=f"  {ASSISTANT_NAME} v1.0  •  Say \"help\" for commands",
            font=(FONT_FAMILY, FONT_TINY_SIZE),
            text_color=TEXT_DIM,
            anchor="w",
        )
        self._footer_label.pack(side="left", padx=12)

        self._engine_label = ctk.CTkLabel(
            status_bar,
            text="Engine: Google STT  •  SAPI5 TTS  ",
            font=(FONT_FAMILY, FONT_TINY_SIZE),
            text_color=TEXT_DIM,
            anchor="e",
        )
        self._engine_label.pack(side="right", padx=12)

    # ═════════════════════════════════════════════════════════════
    # EVENT HANDLERS
    # ═════════════════════════════════════════════════════════════

    def _startup_greeting(self):
        """Play startup greeting."""
        self.command_log.add_jarvis_response("Hello! I'm Jarvis, your personal assistant. Click the mic or press Space to speak.")
        self.command_log.add_system_action("System initialized successfully")

    def _toggle_listen(self):
        """Toggle listening state."""
        if self._is_listening:
            self.voice_engine.stop_listening()
            self._set_ui_state("idle")
            self._is_listening = False
        else:
            self._is_listening = True
            self.voice_engine.start_listening()

    def _on_text_submit(self, event=None):
        """Handle text input submission."""
        text = self._text_input.get().strip()
        if not text:
            return

        self._text_input.delete(0, "end")
        self._process_command(text)

    def _process_command(self, text: str):
        """Route and execute a command."""
        self.command_log.add_user_message(text)
        self._set_ui_state("processing")

        def _do_process():
            result = self.os_kernel.process_command(text)

            # Update UI on main thread
            self.after(0, lambda: self._handle_result(result))

        thread = threading.Thread(target=_do_process, daemon=True)
        thread.start()

    def _handle_result(self, result: dict):
        """Handle command result on the main thread."""
        response = result.get("response", "Done.")
        action = result.get("action", "")
        success = result.get("success", True)

        if success:
            self.command_log.add_jarvis_response(response)
            if action and action != result.get("intent", ""):
                self.command_log.add_system_action(action)
        else:
            self.command_log.add_error(response)

        # Speak the response
        self._set_ui_state("speaking")
        self.voice_engine.speak(response)

    # ─── Voice Engine Callbacks ──────────────────────────────────

    def _on_listening_start(self):
        self.after(0, lambda: self._set_ui_state("listening"))

    def _on_listening_stop(self):
        self.after(0, lambda: self._set_ui_state("idle"))
        self._is_listening = False

    def _on_recognized(self, text: str):
        self.after(0, lambda: self._process_command(text))

    def _on_error(self, error: str):
        self.after(0, lambda: self.command_log.add_error(error))
        self.after(0, lambda: self._set_ui_state("idle"))
        self._is_listening = False

    def _on_speaking_start(self):
        self.after(0, lambda: self._set_ui_state("speaking"))

    def _on_speaking_done(self):
        self.after(0, lambda: self._set_ui_state("idle"))

    # ─── UI State Machine ────────────────────────────────────────

    def _set_ui_state(self, state: str):
        """Update all UI elements for the given state."""
        self.waveform.set_state(state)

        state_config = {
            "idle": {
                "dot_color": ACCENT_CYAN,
                "status": "● Online",
                "status_color": ACCENT_GREEN,
                "mic_fg": BG_LIGHT,
                "mic_text": "🎤",
                "instruction": "Click the mic or press Space to speak",
            },
            "listening": {
                "dot_color": ACCENT_CYAN,
                "status": "● Listening...",
                "status_color": ACCENT_CYAN,
                "mic_fg": ACCENT_CYAN,
                "mic_text": "⏹",
                "instruction": "Listening... speak now",
            },
            "processing": {
                "dot_color": ACCENT_PURPLE,
                "status": "● Processing...",
                "status_color": ACCENT_PURPLE,
                "mic_fg": ACCENT_PURPLE,
                "mic_text": "⏳",
                "instruction": "Processing your command...",
            },
            "speaking": {
                "dot_color": ACCENT_GREEN,
                "status": "● Speaking...",
                "status_color": ACCENT_GREEN,
                "mic_fg": ACCENT_GREEN,
                "mic_text": "🔊",
                "instruction": "Speaking...",
            },
            "error": {
                "dot_color": STATUS_ERROR,
                "status": "● Error",
                "status_color": STATUS_ERROR,
                "mic_fg": BG_LIGHT,
                "mic_text": "🎤",
                "instruction": "Something went wrong. Try again.",
            },
        }

        config = state_config.get(state, state_config["idle"])

        self._status_dot.configure(text_color=config["dot_color"])
        self._status_label.configure(text=config["status"], text_color=config["status_color"])
        self._mic_btn.configure(fg_color=config["mic_fg"], text=config["mic_text"])
        self._instruction_label.configure(text=config["instruction"])

    def _on_close(self):
        """Clean shutdown."""
        self.waveform.stop()
        self.voice_engine.stop_listening()
        self.destroy()
        sys.exit(0)
