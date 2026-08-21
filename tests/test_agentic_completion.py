"""Tests for goal-completion honesty in the ReAct loop.

Regression cover for a run that opened Notepad, never wrote the requested
text, and still reported success:True with the loop's own action-log line
("Called read_ui_elements({})") as the spoken response.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agentic_loop import ReActLoop, StepResult


def _steps(*specs):
    """Build a scratchpad from (tool, succeeded) pairs."""
    return [StepResult(thought="", tool_name=t, tool_args={},
                       observation="ok", succeeded=s) for t, s in specs]


class TestBookkeepingEcho(unittest.TestCase):
    """The loop's internal action log must never be spoken to the user."""

    def test_detects_echo_forms(self):
        for text in ("Called read_ui_elements({})",
                     "Action: open_application({'app_name': 'notepad'})",
                     "  called desktop_interact({'action': 'click'})  ",
                     "Called list_open_windows({})."):
            with self.subTest(text=text):
                self.assertTrue(ReActLoop._is_bookkeeping_echo(text))

    def test_does_not_flag_real_answers(self):
        for text in ("I opened Notepad and wrote the haiku for you, sir.",
                     "The weather in Chennai is 31 degrees.",
                     "I called the number you asked for and left a message.",
                     ""):
            with self.subTest(text=text):
                self.assertFalse(ReActLoop._is_bookkeeping_echo(text))


class TestGoalCompletion(unittest.TestCase):

    def setUp(self):
        self.loop = ReActLoop(max_iterations=5, registry=object())

    def test_goal_achieved_parses_yes_and_no(self):
        for reply, expected in (("YES", True), ("no", False),
                                ("Yes, it was done.", True), ("No - never typed", False)):
            with self.subTest(reply=reply):
                with patch("core.agentic_loop.llm_chat", return_value={"content": reply}):
                    self.assertIs(self.loop._goal_achieved("g", _steps(("t", True))), expected)

    def test_goal_achieved_returns_none_when_unusable(self):
        with patch("core.agentic_loop.llm_chat", return_value={"content": "maybe?"}):
            self.assertIsNone(self.loop._goal_achieved("g", _steps(("t", True))))
        with patch("core.agentic_loop.llm_chat", side_effect=RuntimeError("down")):
            self.assertIsNone(self.loop._goal_achieved("g", _steps(("t", True))))

    def test_no_llm_call_for_empty_scratchpad(self):
        with patch("core.agentic_loop.llm_chat") as chat:
            self.assertIsNone(self.loop._goal_achieved("g", []))
        chat.assert_not_called()


class TestFinalResult(unittest.TestCase):
    """success must reflect the goal, not merely the absence of errors."""

    def setUp(self):
        self.loop = ReActLoop(max_iterations=5, registry=object())
        # The exact shape of the failing run: nothing errored, goal not met.
        self.scratch = _steps(("open_application", True),
                              ("read_ui_elements", None),
                              ("desktop_interact", None))

    def test_unmet_goal_reports_failure_even_when_no_step_failed(self):
        self.assertTrue(self.loop._overall_success(self.scratch),
                        "per-step view should be clean — that's the trap")
        with patch.object(self.loop, "_goal_achieved", return_value=False):
            res = self.loop._final_result("write a haiku", self.scratch, "All done!", 0.0)
        self.assertFalse(res.success)
        self.assertNotIn("All done", res.response)
        self.assertIn("wasn't able to finish", res.response)

    def test_met_goal_reports_success_and_keeps_the_model_message(self):
        with patch.object(self.loop, "_goal_achieved", return_value=True):
            res = self.loop._final_result("write a haiku", self.scratch,
                                          "I wrote the haiku, sir.", 0.0)
        self.assertTrue(res.success)
        self.assertEqual(res.response, "I wrote the haiku, sir.")

    def test_bookkeeping_echo_is_replaced_by_a_real_summary(self):
        with patch.object(self.loop, "_goal_achieved", return_value=True), \
             patch.object(self.loop, "_synthesize_summary", return_value="I opened Notepad."):
            res = self.loop._final_result("g", self.scratch, "Called read_ui_elements({})", 0.0)
        self.assertEqual(res.response, "I opened Notepad.")

    def test_falls_back_to_per_step_view_when_judgement_unavailable(self):
        with patch.object(self.loop, "_goal_achieved", return_value=None):
            res = self.loop._final_result("g", self.scratch, "done", 0.0)
        self.assertTrue(res.success)

        failed = _steps(("open_application", True), ("desktop_interact", False))
        with patch.object(self.loop, "_goal_achieved", return_value=None):
            res = self.loop._final_result("g", failed, "done", 0.0)
        self.assertFalse(res.success, "a failed final step must still fail the run")

    def test_achieved_goal_cannot_override_a_failed_final_step(self):
        failed = _steps(("open_application", True), ("desktop_interact", False))
        with patch.object(self.loop, "_goal_achieved", return_value=True):
            res = self.loop._final_result("g", failed, "done", 0.0)
        self.assertFalse(res.success)


class TestGroqModel(unittest.TestCase):

    def test_default_model_is_not_the_retired_one(self):
        from core import llm_provider
        self.assertNotEqual(llm_provider.GROQ_MODEL, "llama-3.3-70b-versatile",
                            "retired model — 404s on every call")


if __name__ == "__main__":
    unittest.main(verbosity=2)
