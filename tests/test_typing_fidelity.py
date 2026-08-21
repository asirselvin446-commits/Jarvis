"""Tests for reliable text entry.

Regression cover for text arriving corrupted: "Moonlit tides sing" landed as
"Moonlit sssss sing" (keys dropped/repeated at speed) and multi-line text was
flattened onto one line (newlines swallowed).
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.universal_actions import UniversalActions as UA

HAIKU = "Waves whisper on sand,\nMoonlit tides sing soft lullabies,\nEndless blue dreams drift."


class TestClipboardPath(unittest.TestCase):
    """Text is inserted atomically rather than one key event per character."""

    def test_uses_clipboard_by_default(self):
        with patch("core.universal_actions.pyperclip") as clip, \
             patch("core.universal_actions.pyautogui") as gui:
            clip.paste.side_effect = ["old-clip", HAIKU, "old-clip"]
            res = UA.type_text(HAIKU)

        self.assertTrue(res.success)
        self.assertEqual(res.metadata["method"], "clipboard")
        clip.copy.assert_any_call(HAIKU)
        gui.hotkey.assert_called_once_with("ctrl", "v")
        gui.write.assert_not_called()

    def test_restores_the_users_clipboard(self):
        with patch("core.universal_actions.pyperclip") as clip, \
             patch("core.universal_actions.pyautogui"):
            clip.paste.side_effect = ["USER DATA", "typed", "USER DATA"]
            UA.type_text("typed")

        self.assertEqual(clip.copy.call_args_list[-1], call("USER DATA"))

    def test_empty_text_is_a_no_op(self):
        with patch("core.universal_actions.pyperclip") as clip, \
             patch("core.universal_actions.pyautogui") as gui:
            res = UA.type_text("")

        self.assertTrue(res.success)
        clip.copy.assert_not_called()
        gui.hotkey.assert_not_called()

    def test_stale_clipboard_does_not_paste_wrong_content(self):
        """If the clipboard refuses the text, fall back — never paste stale data."""
        with patch("core.universal_actions.pyperclip") as clip, \
             patch("core.universal_actions.pyautogui") as gui:
            # Clipboard is locked by another process: readback != what we set.
            clip.paste.side_effect = ["old", "SOMETHING ELSE", "old"]
            res = UA.type_text("hello")

        gui.hotkey.assert_not_called()
        self.assertEqual(res.metadata["method"], "keystrokes")
        self.assertTrue(res.success)

    def test_falls_back_to_keystrokes_when_clipboard_raises(self):
        with patch("core.universal_actions.pyperclip") as clip, \
             patch("core.universal_actions.pyautogui") as gui:
            clip.paste.return_value = "old"
            clip.copy.side_effect = RuntimeError("clipboard unavailable")
            res = UA.type_text("hello")

        self.assertTrue(res.success)
        self.assertEqual(res.metadata["method"], "keystrokes")
        gui.write.assert_called()


class TestKeystrokeFallback(unittest.TestCase):
    """The fallback path must still reproduce newlines."""

    def test_newlines_become_enter_presses(self):
        with patch("core.universal_actions.pyautogui") as gui:
            UA._write_with_newlines("one\ntwo\nthree", 0.01)

        self.assertEqual(gui.press.call_count, 2, "expected one Enter per newline")
        gui.press.assert_has_calls([call("enter"), call("enter")])
        written = [c.args[0] for c in gui.write.call_args_list]
        self.assertEqual(written, ["one", "two", "three"])

    def test_crlf_is_normalised(self):
        with patch("core.universal_actions.pyautogui") as gui:
            UA._write_with_newlines("a\r\nb", 0.01)

        self.assertEqual(gui.press.call_count, 1)
        self.assertEqual([c.args[0] for c in gui.write.call_args_list], ["a", "b"])

    def test_blank_lines_do_not_emit_empty_writes(self):
        with patch("core.universal_actions.pyautogui") as gui:
            UA._write_with_newlines("a\n\nb", 0.01)

        self.assertEqual(gui.press.call_count, 2)
        self.assertEqual([c.args[0] for c in gui.write.call_args_list], ["a", "b"])

    def test_force_keystrokes_skips_the_clipboard(self):
        with patch("core.universal_actions.pyperclip") as clip, \
             patch("core.universal_actions.pyautogui") as gui:
            res = UA.type_text("secret", force_keystrokes=True)

        clip.copy.assert_not_called()
        gui.hotkey.assert_not_called()
        gui.write.assert_called()
        self.assertEqual(res.metadata["method"], "keystrokes")


class TestCallersUseReliableTyping(unittest.TestCase):
    """The two agent-facing typing paths must not hand-roll their own."""

    def test_computer_use_does_not_call_typewrite(self):
        import inspect
        from plugins import computer_use
        src = inspect.getsource(computer_use._execute_action)
        self.assertNotIn("pyautogui.typewrite", src)
        self.assertIn("UniversalActions.type_text", src)

    def test_desktop_interact_does_not_use_type_keys(self):
        """pywinauto type_keys reads {}, +, ^, %, ~ as key syntax — unsafe for text."""
        import inspect
        from plugins import accessibility_agent
        src = inspect.getsource(accessibility_agent._perform_action)
        # Match the call, not the comment explaining why it's gone.
        self.assertNotIn("control.type_keys(", src)
        self.assertIn("UniversalActions.type_text", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
