"""
J.A.R.V.I.S. Waveform Visualizer
Animated canvas-based audio waveform with multiple animation states:
  - IDLE: gentle breathing pulse
  - LISTENING: active bouncing bars
  - PROCESSING: spinning/morphing pattern
  - SPEAKING: rhythmic wave
"""

import tkinter as tk
import math
import random

from ui.theme import (
    BG_DARKEST, BG_DARK,
    WAVE_IDLE, WAVE_ACTIVE, WAVE_GLOW,
    ACCENT_CYAN, ACCENT_PURPLE, ACCENT_GREEN, STATUS_ERROR,
    WAVE_BAR_COUNT, WAVE_BAR_WIDTH, WAVE_BAR_GAP, WAVE_MAX_HEIGHT,
    ANIMATION_FPS,
)


class WaveformVisualizer(tk.Canvas):
    """
    Animated waveform that responds to assistant state.
    States: 'idle', 'listening', 'processing', 'speaking', 'error'
    """

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("bg", BG_DARKEST)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("height", 180)
        super().__init__(parent, **kwargs)

        self._state = "idle"
        self._frame = 0
        self._target_heights = [0.0] * WAVE_BAR_COUNT
        self._current_heights = [0.0] * WAVE_BAR_COUNT
        self._running = True
        self._anim_id = None

        # Start animation loop
        self._animate()

    # ─── State Control ───────────────────────────────────────────

    def set_state(self, state: str):
        """Set animation state: 'idle', 'listening', 'processing', 'speaking', 'error'."""
        self._state = state
        self._frame = 0

    def stop(self):
        """Stop animation loop."""
        self._running = False
        if self._anim_id:
            self.after_cancel(self._anim_id)

    # ─── Animation Loop ─────────────────────────────────────────

    def _animate(self):
        if not self._running:
            return

        self._frame += 1
        self._update_heights()
        self._draw()

        interval = max(16, 1000 // ANIMATION_FPS)
        self._anim_id = self.after(interval, self._animate)

    def _update_heights(self):
        """Compute target heights based on current state."""
        t = self._frame * 0.05  # time variable

        if self._state == "idle":
            for i in range(WAVE_BAR_COUNT):
                # Gentle sine wave breathing
                phase = i / WAVE_BAR_COUNT * math.pi * 2
                self._target_heights[i] = (
                    0.15 + 0.08 * math.sin(t * 0.8 + phase)
                )

        elif self._state == "listening":
            for i in range(WAVE_BAR_COUNT):
                # Active randomized bars with center emphasis
                center = WAVE_BAR_COUNT / 2
                dist = abs(i - center) / center
                base = max(0.1, 1.0 - dist * 0.7)
                noise = random.uniform(0.3, 1.0)
                wave = 0.3 * math.sin(t * 2 + i * 0.4)
                self._target_heights[i] = base * (noise * 0.6 + wave * 0.4)

        elif self._state == "processing":
            for i in range(WAVE_BAR_COUNT):
                # Rotating wave pattern
                phase = i / WAVE_BAR_COUNT * math.pi * 4
                self._target_heights[i] = (
                    0.3 + 0.35 * math.sin(t * 3 + phase)
                )

        elif self._state == "speaking":
            for i in range(WAVE_BAR_COUNT):
                # Rhythmic speaking pattern
                phase = i / WAVE_BAR_COUNT * math.pi * 2
                self._target_heights[i] = (
                    0.2 + 0.4 * abs(math.sin(t * 1.5 + phase * 2))
                )

        elif self._state == "error":
            for i in range(WAVE_BAR_COUNT):
                self._target_heights[i] = 0.05

        # Smooth interpolation
        lerp_speed = 0.15
        for i in range(WAVE_BAR_COUNT):
            self._current_heights[i] += (
                (self._target_heights[i] - self._current_heights[i]) * lerp_speed
            )

    def _draw(self):
        """Render the waveform bars onto the canvas."""
        self.delete("all")

        w = self.winfo_width()
        h = self.winfo_height()

        if w <= 1 or h <= 1:
            return

        center_y = h / 2
        total_bar_width = WAVE_BAR_WIDTH + WAVE_BAR_GAP
        total_width = total_bar_width * WAVE_BAR_COUNT
        start_x = (w - total_width) / 2

        # Choose color based on state
        if self._state == "idle":
            bar_color = WAVE_IDLE
            glow_color = None
        elif self._state == "listening":
            bar_color = ACCENT_CYAN
            glow_color = WAVE_GLOW
        elif self._state == "processing":
            bar_color = ACCENT_PURPLE
            glow_color = ACCENT_PURPLE
        elif self._state == "speaking":
            bar_color = ACCENT_GREEN
            glow_color = ACCENT_GREEN
        elif self._state == "error":
            bar_color = STATUS_ERROR
            glow_color = None
        else:
            bar_color = WAVE_IDLE
            glow_color = None

        # Draw center line (very subtle)
        self.create_line(
            start_x - 10, center_y,
            start_x + total_width + 10, center_y,
            fill="#0d1230", width=1
        )

        # Draw bars (mirrored top and bottom)
        for i in range(WAVE_BAR_COUNT):
            x = start_x + i * total_bar_width
            bar_h = self._current_heights[i] * WAVE_MAX_HEIGHT

            # Top bar
            self.create_rectangle(
                x, center_y - bar_h,
                x + WAVE_BAR_WIDTH, center_y - 1,
                fill=bar_color, outline="", width=0
            )
            # Bottom bar (mirror)
            self.create_rectangle(
                x, center_y + 1,
                x + WAVE_BAR_WIDTH, center_y + bar_h,
                fill=bar_color, outline="", width=0
            )

            # Glow effect on active bars (for listening/speaking)
            if glow_color and self._current_heights[i] > 0.3:
                alpha_bar_h = bar_h * 1.3
                glow_fill = self._dim_color(glow_color, 0.15)
                self.create_rectangle(
                    x - 1, center_y - alpha_bar_h,
                    x + WAVE_BAR_WIDTH + 1, center_y + alpha_bar_h,
                    fill=glow_fill, outline="", width=0
                )

        # Draw status text overlay
        status_text = {
            "idle": "Ready",
            "listening": "● Listening...",
            "processing": "Processing...",
            "speaking": "Speaking...",
            "error": "Error",
        }.get(self._state, "")

        text_color = {
            "idle": "#4a5278",
            "listening": ACCENT_CYAN,
            "processing": ACCENT_PURPLE,
            "speaking": ACCENT_GREEN,
            "error": STATUS_ERROR,
        }.get(self._state, "#4a5278")

        self.create_text(
            w / 2, h - 20,
            text=status_text,
            fill=text_color,
            font=("Segoe UI", 10, "bold"),
            anchor="center"
        )

    @staticmethod
    def _dim_color(hex_color: str, factor: float) -> str:
        """Dim a hex color by a factor (0-1)."""
        hex_color = hex_color.lstrip("#")
        r = int(int(hex_color[0:2], 16) * factor)
        g = int(int(hex_color[2:4], 16) * factor)
        b = int(int(hex_color[4:6], 16) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"
