"""
J.A.R.V.I.S. Performance Monitor
Self-monitoring and optimization for the voice pipeline.
Tracks latency, accuracy, resource usage, and suggests optimizations.
"""

import time
import logging
import statistics
from collections import deque
from typing import Optional

logger = logging.getLogger("jarvis.performance")


class PerformanceMonitor:
    """
    Monitors voice pipeline performance metrics and suggests optimizations.

    Tracked metrics:
      - Wake word detection latency
      - STT transcription latency
      - End-to-end response latency
      - Recognition corrections (accuracy proxy)
      - CPU/RAM usage trends
      - Noise level trends
    """

    MAX_SAMPLES = 100  # Rolling window size

    def __init__(self):
        self.metrics = {
            "wake_detection_ms": deque(maxlen=self.MAX_SAMPLES),
            "stt_latency_ms": deque(maxlen=self.MAX_SAMPLES),
            "processing_latency_ms": deque(maxlen=self.MAX_SAMPLES),
            "tts_latency_ms": deque(maxlen=self.MAX_SAMPLES),
            "total_response_ms": deque(maxlen=self.MAX_SAMPLES),
            "corrections_count": 0,
            "commands_count": 0,
            "errors_count": 0,
            "noise_levels_db": deque(maxlen=self.MAX_SAMPLES),
        }

        # Timing helpers
        self._timers: dict[str, float] = {}

    # ── Timer API ────────────────────────────────────────────────

    def start_timer(self, name: str):
        """Start a named timer."""
        self._timers[name] = time.perf_counter()

    def stop_timer(self, name: str) -> float:
        """Stop a named timer and return elapsed milliseconds."""
        if name not in self._timers:
            return 0.0
        elapsed_ms = (time.perf_counter() - self._timers[name]) * 1000
        del self._timers[name]

        # Auto-record to metrics
        metric_key = f"{name}_ms"
        if metric_key in self.metrics and isinstance(self.metrics[metric_key], deque):
            self.metrics[metric_key].append(elapsed_ms)

        return elapsed_ms

    # ── Record metrics ───────────────────────────────────────────

    def record_command(self):
        """Record that a command was processed."""
        self.metrics["commands_count"] += 1

    def record_correction(self):
        """Record that a correction was detected (user had to repeat/fix)."""
        self.metrics["corrections_count"] += 1

    def record_error(self):
        """Record that an error occurred."""
        self.metrics["errors_count"] += 1

    def record_noise_level(self, db: float):
        """Record ambient noise level."""
        self.metrics["noise_levels_db"].append(db)

    # ── Reporting ────────────────────────────────────────────────

    def get_report(self) -> dict:
        """Get a comprehensive performance report."""
        report = {}

        for key in ["wake_detection_ms", "stt_latency_ms", "processing_latency_ms",
                     "tts_latency_ms", "total_response_ms"]:
            values = list(self.metrics[key])
            if values:
                report[key] = {
                    "avg": round(statistics.mean(values), 1),
                    "p50": round(statistics.median(values), 1),
                    "p95": round(sorted(values)[int(len(values) * 0.95)], 1) if len(values) >= 20 else None,
                    "min": round(min(values), 1),
                    "max": round(max(values), 1),
                    "samples": len(values),
                }
            else:
                report[key] = {"avg": None, "samples": 0}

        report["commands_count"] = self.metrics["commands_count"]
        report["corrections_count"] = self.metrics["corrections_count"]
        report["errors_count"] = self.metrics["errors_count"]

        # Accuracy estimate
        total_cmds = self.metrics["commands_count"]
        corrections = self.metrics["corrections_count"]
        if total_cmds > 0:
            report["accuracy_pct"] = round((1 - corrections / total_cmds) * 100, 1)
        else:
            report["accuracy_pct"] = None

        # Noise levels
        noise_values = list(self.metrics["noise_levels_db"])
        if noise_values:
            report["avg_noise_db"] = round(statistics.mean(noise_values), 1)
        else:
            report["avg_noise_db"] = None

        return report

    def get_summary_text(self) -> str:
        """Get a human-readable performance summary."""
        r = self.get_report()
        lines = ["J.A.R.V.I.S. Performance Report:"]

        if r.get("total_response_ms", {}).get("avg") is not None:
            avg = r["total_response_ms"]["avg"]
            lines.append(f"  Average response time: {avg:.0f}ms")

        if r.get("stt_latency_ms", {}).get("avg") is not None:
            avg = r["stt_latency_ms"]["avg"]
            lines.append(f"  Average STT latency: {avg:.0f}ms")

        if r.get("commands_count", 0) > 0:
            lines.append(f"  Commands processed: {r['commands_count']}")

        if r.get("accuracy_pct") is not None:
            lines.append(f"  Recognition accuracy: {r['accuracy_pct']}%")

        if r.get("errors_count", 0) > 0:
            lines.append(f"  Errors: {r['errors_count']}")

        return "\n".join(lines)

    # ── Optimization suggestions ─────────────────────────────────

    def suggest_optimizations(self) -> list[str]:
        """Analyze metrics and suggest improvements."""
        suggestions = []
        r = self.get_report()

        # Check STT latency
        stt = r.get("stt_latency_ms", {})
        if stt.get("avg") and stt["avg"] > 3000:
            suggestions.append(
                "STT latency is high (avg {:.0f}ms). Consider using a smaller model "
                "(tiny.en) or enabling GPU for STT.".format(stt["avg"])
            )

        # Check total response time
        total = r.get("total_response_ms", {})
        if total.get("avg") and total["avg"] > 8000:
            suggestions.append(
                "Total response time is high (avg {:.0f}ms). The LLM processing "
                "may be the bottleneck. Consider a faster model.".format(total["avg"])
            )

        # Check accuracy
        if r.get("accuracy_pct") is not None and r["accuracy_pct"] < 80:
            suggestions.append(
                "Recognition accuracy is low ({:.0f}%). Consider upgrading the STT "
                "model to 'small.en' for better accuracy.".format(r["accuracy_pct"])
            )

        # Check noise
        if r.get("avg_noise_db") is not None and r["avg_noise_db"] > -25:
            suggestions.append(
                "High ambient noise detected (avg {:.0f}dB). Consider using a "
                "directional microphone or enabling noise suppression.".format(r["avg_noise_db"])
            )

        return suggestions


# ── Global singleton ─────────────────────────────────────────────
_instance: PerformanceMonitor | None = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor singleton."""
    global _instance
    if _instance is None:
        _instance = PerformanceMonitor()
    return _instance
