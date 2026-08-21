"""Tests for the OCR engine and the computer-use context it feeds.

The Windows OCR path is exercised against a generated image so the assertions
don't depend on whatever happens to be on screen.
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont

from core.ocr_engine import _ps_quote, _windows_ocr, _windows_ocr_words


def _make_text_image(text: str, size=(900, 220)) -> str:
    """Render text to a temp PNG that Windows OCR can read reliably."""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    font = None
    for candidate in (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf"):
        if os.path.exists(candidate):
            font = ImageFont.truetype(candidate, 56)
            break
    draw.text((30, 70), text, fill="black", font=font)
    path = os.path.join(tempfile.gettempdir(), "jarvis_ocr_unittest.png")
    img.save(path, format="PNG")
    return path


class TestPowerShellQuoting(unittest.TestCase):
    """Paths are interpolated into PowerShell; they must not be able to break out."""

    def test_plain_path(self):
        self.assertEqual(_ps_quote(r"C:\tmp\a.png"), r"'C:\tmp\a.png'")

    def test_single_quote_is_doubled(self):
        self.assertEqual(_ps_quote("it's.png"), "'it''s.png'")

    def test_dollar_and_backtick_are_not_interpolated(self):
        """Single-quoted PS strings are literal, so these pass through intact."""
        quoted = _ps_quote(r"C:\$env:TEMP\a`b.png")
        self.assertTrue(quoted.startswith("'") and quoted.endswith("'"))
        self.assertIn("$env:TEMP", quoted)
        self.assertIn("a`b", quoted)


@unittest.skipUnless(sys.platform == "win32", "Windows OCR is Windows-only")
class TestWindowsOCR(unittest.TestCase):
    """Regression tests for the WinRT OCR path.

    These previously returned nothing at all: the PowerShell helper called
    GetAwaiter() on a WinRT IAsyncOperation, which is a COM object and has no
    such method, and the failure was swallowed by a bare catch.
    """

    @classmethod
    def setUpClass(cls):
        cls.text = "Hello Jarvis 12345"
        cls.path = _make_text_image(cls.text)

    def test_windows_ocr_reads_text(self):
        out = _windows_ocr(self.path)
        self.assertTrue(out, "Windows OCR returned nothing (WinRT Await regression?)")
        self.assertIn("Jarvis", out)

    def test_windows_ocr_words_returns_boxes(self):
        words = _windows_ocr_words(self.path)
        self.assertTrue(words, "Windows OCR word extraction returned nothing")
        for w in words:
            with self.subTest(word=w.get("text")):
                for key in ("text", "x", "y", "w", "h"):
                    self.assertIn(key, w)
                self.assertGreater(w["w"], 0)
                self.assertGreater(w["h"], 0)

    def test_line_box_spans_whole_line_not_just_first_word(self):
        """The box must cover every word, so its centre lands mid-line.

        It used to use only the first word's rect, which put the click target
        on the line's opening character.
        """
        words = _windows_ocr_words(self.path)
        line = max(words, key=lambda w: len(w.get("text", "")))
        self.assertIn(" ", line["text"], "expected a multi-word line to test against")
        # A multi-word line rendered at 56px is far wider than one short word.
        self.assertGreater(line["w"], 200,
                           f"line box too narrow ({line['w']}px) — first-word-only regression")

    def test_missing_file_returns_empty_not_crash(self):
        self.assertEqual(_windows_ocr(r"C:\nope\missing.png"), "")
        self.assertEqual(_windows_ocr_words(r"C:\nope\missing.png"), [])


class TestComputerUseContextFallback(unittest.TestCase):
    """computer_use must still get coordinates when the a11y tree is empty."""

    def test_falls_back_to_ocr_when_accessibility_empty(self):
        from plugins import computer_use as cu

        class FakeEl:
            def __init__(self, text, x, y, clickable=True, category="Button"):
                self.text, self.center_x, self.center_y = text, x, y
                self.clickable, self.category = clickable, category

        with patch("core.accessibility.get_clickable_elements", return_value=[]), \
             patch("core.ocr_engine.semantic_ocr_screen",
                   return_value=[FakeEl("Send", 400, 300)]):
            ctx = cu._get_accessibility_context()

        self.assertIn("Send", ctx)
        self.assertIn("(400, 300)", ctx)
        self.assertIn("OCR-detected", ctx)

    def test_prefers_accessibility_tree_when_available(self):
        from plugins import computer_use as cu

        a11y = [{"Name": "Save", "ControlType": "ControlType.Button",
                 "CenterX": 100, "CenterY": 200, "IsEnabled": True}]
        with patch("core.accessibility.get_clickable_elements", return_value=a11y), \
             patch("core.ocr_engine.semantic_ocr_screen") as ocr:
            ctx = cu._get_accessibility_context()

        ocr.assert_not_called()
        self.assertIn("Accessibility-detected", ctx)
        self.assertIn("Save", ctx)

    def test_returns_empty_when_both_sources_fail(self):
        from plugins import computer_use as cu

        with patch("core.accessibility.get_clickable_elements", side_effect=RuntimeError("no a11y")), \
             patch("core.ocr_engine.semantic_ocr_screen", side_effect=RuntimeError("no ocr")):
            self.assertEqual(cu._get_accessibility_context(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
