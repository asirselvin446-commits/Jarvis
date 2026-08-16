"""
Tests for streaming STT transcript cleaning — the hallucination / noise filter
that stops Jarvis from acting on phantom speech Whisper invents on silence.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.streaming_stt import _clean_transcript


class TestTranscriptCleaning:
    def test_drops_common_whisper_hallucinations(self):
        for junk in ["Thanks for watching!", "Thank you", "Please subscribe",
                     "you", "Subscribe", "  thank you.  "]:
            assert _clean_transcript(junk) == "", junk

    def test_drops_pure_punctuation_and_noise(self):
        for junk in [".....", "...", "♪♪", "   ", ""]:
            assert _clean_transcript(junk) == "", repr(junk)

    def test_drops_repeated_token_noise(self):
        assert _clean_transcript("you you you") == ""
        assert _clean_transcript("no no no no") == ""

    def test_keeps_real_commands(self):
        for cmd in ["open chrome", "set volume to fifty",
                    "play despacito on youtube", "what's the weather"]:
            assert _clean_transcript(cmd) == cmd, cmd

    def test_strips_surrounding_whitespace_only(self):
        assert _clean_transcript("  play music  ") == "play music"
