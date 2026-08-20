"""
Tests for systematic tool-result verification in the ReAct loop.

Core guarantee: Jarvis must never report success for actions that failed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agentic_loop import ReActLoop, StepResult


def _step(tool="do_thing", observation="ok", succeeded=None):
    return StepResult(thought="t", tool_name=tool, tool_args={},
                      observation=observation, succeeded=succeeded)


class TestVerifyObservation:
    def test_error_string_is_failure(self):
        assert ReActLoop._verify_observation("Error: Tool 'x' not found.") is False

    def test_error_dict_is_failure(self):
        assert ReActLoop._verify_observation({"error": "Execution failed for 'x'"}) is False

    def test_traceback_is_failure(self):
        obs = "Traceback (most recent call last):\n  File ..."
        assert ReActLoop._verify_observation(obs) is False

    def test_plugin_failure_string(self):
        assert ReActLoop._verify_observation("Failed to read emails: timeout") is False
        assert ReActLoop._verify_observation("IMAP login failed: bad creds") is False

    def test_success_string(self):
        assert ReActLoop._verify_observation("Successfully opened Chrome.") is True
        assert ReActLoop._verify_observation("Email sent to a@b.com.") is True

    def test_unclear_returns_none(self):
        assert ReActLoop._verify_observation("42") is None
        assert ReActLoop._verify_observation("") is None

    def test_earliest_signal_wins(self):
        """A success result quoting failure words in its payload is still success."""
        obs = "Sent WhatsApp message to 'Ravi': 'sorry I could not make it tonight'"
        assert ReActLoop._verify_observation(obs) is True

    def test_failure_first_still_failure(self):
        obs = "Could not find contact 'Ravi'. Message was not sent."
        assert ReActLoop._verify_observation(obs) is False


class TestOverallSuccess:
    def test_no_steps_is_success(self):
        """A conversational answer with no tool calls isn't a failure."""
        assert ReActLoop._overall_success([]) is True

    def test_all_failed_is_failure(self):
        steps = [_step(succeeded=False), _step(succeeded=False)]
        assert ReActLoop._overall_success(steps) is False

    def test_final_step_failed_is_failure(self):
        steps = [_step(succeeded=True), _step(succeeded=False)]
        assert ReActLoop._overall_success(steps) is False

    def test_recovered_failure_is_success(self):
        """A failed step followed by a successful retry is a successful run."""
        steps = [_step(succeeded=False), _step(succeeded=True)]
        assert ReActLoop._overall_success(steps) is True

    def test_unclear_steps_are_not_failures(self):
        assert ReActLoop._overall_success([_step(succeeded=None)]) is True


class TestSummariesAreHonest:
    def test_deterministic_summary_names_failures(self):
        steps = [_step(tool="open_app", succeeded=True),
                 _step(tool="send_email", succeeded=False)]
        out = ReActLoop._deterministic_summary(steps)
        assert "send_email" in out
        assert "failed" in out.lower()

    def test_deterministic_summary_clean_when_all_ok(self):
        steps = [_step(tool="open_app", succeeded=True)]
        out = ReActLoop._deterministic_summary(steps)
        assert "failed" not in out.lower()

    def test_no_steps_message(self):
        assert "hadn't completed any" in ReActLoop._deterministic_summary([])
