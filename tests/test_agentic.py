"""
Tests for the agentic ReAct brain and its routing.

Covers:
  * ReActLoop control flow (act → observe → finish)
  * Loop guard: identical repeated calls are capped and the workflow ends
  * Final-summary synthesis fallback
  * Orchestrator routing gate (_is_agentic_goal) for simple vs. multi-step goals

All tests mock the LLM and tool registry, so nothing touches the network,
the microphone, or the real system.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _FakeRegistry:
    """Stand-in for AgenticToolRegistry that records calls instead of running tools."""

    def __init__(self):
        self.calls = []

    def get_tool_schemas_for_llm(self):
        return []

    def execute(self, name, args):
        self.calls.append((name, args))
        return f"ok:{name}"


def _tool_call(name, args):
    return {"content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


class TestReActLoop:
    def test_completes_multi_step_then_finishes(self, monkeypatch):
        import core.agentic_loop as al

        seq = [
            _tool_call("open_app", {"n": "notepad"}),
            _tool_call("write_file", {"t": "hi"}),
            {"content": "Opened Notepad and wrote the note, sir.", "tool_calls": []},
        ]
        state = {"i": 0}

        def fake_chat(messages, tools=None, temperature=0.0, timeout=60):
            r = seq[state["i"]]
            state["i"] += 1
            return r

        monkeypatch.setattr(al, "llm_chat", fake_chat)
        reg = _FakeRegistry()
        res = al.ReActLoop(max_iterations=6, registry=reg).run("do two things", context="")

        assert res.success is True
        assert len(res.steps) == 2
        assert reg.calls == [("open_app", {"n": "notepad"}), ("write_file", {"t": "hi"})]
        assert "Notepad" in res.response

    def test_loop_guard_caps_repeated_calls(self, monkeypatch):
        import core.agentic_loop as al

        stuck = _tool_call("retry", {"x": 1})
        monkeypatch.setattr(al, "llm_chat",
                            lambda messages, tools=None, temperature=0.0, timeout=60: stuck)

        reg = _FakeRegistry()
        res = al.ReActLoop(max_iterations=20, registry=reg).run("impossible", context="")

        # The identical call is executed at most MAX_REPEAT times, then the loop
        # ends instead of burning the whole iteration budget.
        assert reg.calls.count(("retry", {"x": 1})) == al.ReActLoop.MAX_REPEAT
        assert res.response  # a summary is always produced

    def test_summary_fallback_when_llm_summary_fails(self, monkeypatch):
        import core.agentic_loop as al

        def boom(messages, tools=None, temperature=0.0, timeout=60):
            raise RuntimeError("no llm")

        monkeypatch.setattr(al, "llm_chat", boom)
        loop = al.ReActLoop(registry=_FakeRegistry())
        from core.agentic_loop import StepResult

        steps = [StepResult("t", "open_app", {}, "done")]
        text = loop._synthesize_summary("goal", steps)
        assert "step" in text.lower()

        # No steps at all -> graceful message.
        assert loop._synthesize_summary("goal", []) != ""


class TestAgenticRouting:
    def test_simple_commands_stay_on_fast_path(self):
        from core.orchestrator import Orchestrator

        o = Orchestrator()
        for cmd in ["what time is it", "open chrome", "set volume to 50",
                    "play music on youtube", "search google for weather"]:
            assert o._is_agentic_goal(cmd) is False, cmd

    def test_multi_step_goals_route_to_agentic(self):
        from core.orchestrator import Orchestrator

        o = Orchestrator()
        for cmd in [
            "open my email and find the invoice then download it",
            "research the top 3 laptops and make a comparison",
            "keep checking my downloads until the file appears",
            "organize my desktop files by type",
        ]:
            assert o._is_agentic_goal(cmd) is True, cmd

    def test_flag_disables_agentic_routing(self):
        from core.orchestrator import Orchestrator

        o = Orchestrator()
        o.agentic_enabled = False
        assert o._is_agentic_goal("open email and then download the invoice") is False
