"""
Tests for microphone gain normalization in core.streaming_stt — the fix for
"I have to shout". Verifies quiet speech is boosted, while silence and
already-loud audio are left alone and nothing ever clips.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.streaming_stt import StreamingSTT


def _stt(**kw):
    """A StreamingSTT without loading any model or opening a mic."""
    return StreamingSTT(**kw)


def _peak(a):
    return int(np.max(np.abs(a.astype(np.int32))))


class TestGainNormalization:
    def test_quiet_speech_is_boosted(self):
        stt = _stt(gain_target_peak=0.95, gain_max=12.0, gain_noise_floor=200)
        # Peak ~4000 needs ~7.8x to reach target — within the 12x cap.
        quiet = (np.sin(np.linspace(0, 50, 1600)) * 4000).astype(np.int16)
        out = stt._normalize_gain(quiet)
        assert _peak(out) > _peak(quiet)
        # Boosted to near the target (0.95 * 32767 ≈ 31128).
        assert _peak(out) >= 25000

    def test_very_quiet_speech_boosted_to_cap(self):
        """A faint signal that can't reach target within the cap is still boosted maximally."""
        stt = _stt(gain_target_peak=0.95, gain_max=12.0, gain_noise_floor=200)
        quiet = (np.sin(np.linspace(0, 50, 1600)) * 1000).astype(np.int16)  # peak ~1000
        out = stt._normalize_gain(quiet)
        # Capped at 12x → ~12000, clearly boosted but not to target.
        assert 10000 <= _peak(out) <= 12500

    def test_silence_left_untouched(self):
        stt = _stt(gain_noise_floor=200)
        near_silence = (np.random.randint(-50, 50, 1600)).astype(np.int16)  # peak < floor
        out = stt._normalize_gain(near_silence)
        assert np.array_equal(out, near_silence)

    def test_loud_audio_left_untouched(self):
        stt = _stt(gain_target_peak=0.95)
        loud = (np.sin(np.linspace(0, 50, 1600)) * 32000).astype(np.int16)
        out = stt._normalize_gain(loud)
        assert np.array_equal(out, loud)

    def test_max_gain_cap_respected(self):
        # Very faint signal (peak ~300) with a low cap must not exceed the cap.
        stt = _stt(gain_target_peak=0.95, gain_max=4.0, gain_noise_floor=200)
        faint = (np.sin(np.linspace(0, 50, 1600)) * 300).astype(np.int16)
        out = stt._normalize_gain(faint)
        assert _peak(out) <= _peak(faint) * 4 + 1

    def test_never_clips(self):
        stt = _stt(gain_target_peak=0.95, gain_max=100.0)
        sig = (np.sin(np.linspace(0, 50, 1600)) * 5000).astype(np.int16)
        out = stt._normalize_gain(sig)
        assert _peak(out) <= 32767

    def test_disabled_is_passthrough(self):
        stt = _stt(gain_enabled=False)
        quiet = (np.sin(np.linspace(0, 50, 1600)) * 1000).astype(np.int16)
        out = stt._normalize_gain(quiet)
        assert np.array_equal(out, quiet)

    def test_empty_audio_safe(self):
        stt = _stt()
        out = stt._normalize_gain(np.array([], dtype=np.int16))
        assert len(out) == 0

    def test_output_dtype_is_int16(self):
        stt = _stt()
        quiet = (np.sin(np.linspace(0, 50, 1600)) * 1000).astype(np.int16)
        out = stt._normalize_gain(quiet)
        assert out.dtype == np.int16
