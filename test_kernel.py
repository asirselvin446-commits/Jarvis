"""Master system integrity suite for the Jarvis AI OS.

Tests the *current* architecture: a unified Orchestrator that routes every
command through either the regex fast path, a single-shot tool call, or the
multi-step agentic ReAct loop. Nothing here performs real side effects --
fast-path tests stub out tool execution so the suite never opens a browser,
changes volume, or sends a message.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.os_kernel import OSKernel
from core.orchestrator import Orchestrator

# Capability domains Jarvis claims to cover. Each maps to tools that must be
# registered for that domain to actually work end to end.
REQUIRED_CAPABILITIES = {
    "web":         ["open_website", "search_google", "web_scrape", "browser_agent"],
    "system":      ["set_volume", "get_system_status", "run_powershell", "manage_power"],
    "files":       ["find_files", "open_file", "move_file", "copy_file", "delete_file"],
    "coding":      ["read_code_file", "write_code_file", "git_status", "git_commit"],
    "vision":      ["take_screenshot", "analyze_screen", "get_screen_text", "computer_use"],
    "memory":      ["remember_fact", "recall_fact", "store_knowledge", "query_knowledge"],
    "comms":       ["send_email", "read_emails", "whatsapp_send_message", "send_chat_message"],
    "scheduling":  ["set_reminder", "set_timer", "set_alarm", "set_cron_job"],
    "windows":     ["list_open_windows", "switch_window", "snap_window", "close_application"],
    "self_evolve": ["create_jarvis_plugin", "learn_new_skill", "build_with_claude", "create_skill"],
    "safety":      ["emergency_stop", "resume_after_stop"],
}


class TestKernelBoot(unittest.TestCase):
    """The kernel must boot cleanly and wire up its subsystems."""

    @classmethod
    def setUpClass(cls):
        cls.kernel = OSKernel()
        cls.orch = cls.kernel.orchestrator

    def test_kernel_is_singleton(self):
        """Repeated construction must reuse one kernel (plugins boot on import)."""
        self.assertIs(OSKernel(), self.kernel)

    def test_subsystems_wired(self):
        for attr in ("memory", "tool_manager", "planner", "verification", "bus"):
            with self.subTest(subsystem=attr):
                self.assertIsNotNone(getattr(self.orch, attr, None),
                                     "Orchestrator.%s is not wired" % attr)

    def test_agentic_brain_enabled_by_default(self):
        self.assertTrue(self.orch.agentic_enabled,
                        "Agentic ReAct brain should be on unless JARVIS_AGENTIC_MODE=0")


class TestToolRegistry(unittest.TestCase):
    """Every registered tool must be well formed and callable."""

    @classmethod
    def setUpClass(cls):
        cls.tools = OSKernel().orchestrator.tool_manager.tools

    def test_tool_count(self):
        print("\n[+] Registered tools: %d" % len(self.tools))
        self.assertGreaterEqual(len(self.tools), 140,
                                "Tool count dropped -- a plugin likely failed to load")

    def test_every_tool_is_well_formed(self):
        for name, spec in self.tools.items():
            with self.subTest(tool=name):
                self.assertTrue(callable(spec.get("func")), "%s has no callable func" % name)
                self.assertTrue(spec.get("description"), "%s has no description" % name)
                params = spec.get("parameters")
                self.assertIsInstance(params, dict, "%s has no parameter schema" % name)
                self.assertEqual(params.get("type"), "object",
                                 "%s parameter schema is not a JSON-schema object" % name)

    def test_dangerous_tools_are_flagged(self):
        """Destructive tools must be marked so the confirmation layer can gate them."""
        for name in ("delete_file", "kill_process", "run_powershell"):
            with self.subTest(tool=name):
                spec = self.tools.get(name)
                self.assertIsNotNone(spec, "%s is not registered" % name)
                self.assertTrue(spec.get("is_dangerous") or spec.get("requires_confirmation"),
                                "%s is destructive but is not gated" % name)

    def test_all_capability_domains_covered(self):
        missing = {}
        for domain, required in REQUIRED_CAPABILITIES.items():
            gaps = [t for t in required if t not in self.tools]
            if gaps:
                missing[domain] = gaps
        self.assertEqual(missing, {}, "Capability gaps by domain: %s" % missing)


class TestAgenticRouting(unittest.TestCase):
    """Multi-step goals go to the ReAct loop; simple commands stay fast."""

    @classmethod
    def setUpClass(cls):
        cls.orch = OSKernel().orchestrator

    def test_multi_step_goals_route_to_agentic_loop(self):
        goals = [
            "open Spotify and play a song",
            "open Notepad and write a haiku",
            "research the best laptops and email me a summary",
            "find out who won the game then tell me the score",
            "go through my inbox and organize it",
            "keep checking the build until it passes",
            "clean up my downloads folder",
        ]
        for goal in goals:
            with self.subTest(goal=goal):
                self.assertTrue(self.orch._is_agentic_goal(goal),
                                "Should be agentic: %r" % goal)

    def test_simple_commands_stay_on_fast_path(self):
        simple = [
            "open youtube",
            "set volume to 50",
            "what is my battery status",
            "take a screenshot",
            "mute the volume",
            "what is the meaning of life",
        ]
        for cmd in simple:
            with self.subTest(command=cmd):
                self.assertFalse(self.orch._is_agentic_goal(cmd),
                                 "Should NOT be agentic: %r" % cmd)

    def test_agentic_mode_can_be_disabled(self):
        with patch.dict(os.environ, {"JARVIS_AGENTIC_MODE": "0"}):
            orch = Orchestrator()
            self.assertFalse(orch.agentic_enabled)
            self.assertFalse(orch._is_agentic_goal("open Spotify and play a song"))

    def test_agentic_loop_is_built_and_cached(self):
        """The ReAct loop must reach every registered tool, not a subset."""
        loop = self.orch._get_agentic_loop()
        self.assertIsNotNone(loop)
        self.assertIs(self.orch._get_agentic_loop(), loop, "loop should be cached")


class TestDangerousToolGate(unittest.TestCase):
    """Declared safety flags must be enforced on the single-shot path too."""

    def setUp(self):
        self.orch = OSKernel().orchestrator
        self.orch._pending_action = None
        self.orch.autonomy = "guarded"

    def _call(self, tool, args):
        return [{"function": {"name": tool, "arguments": args}}]

    def test_dangerous_tool_is_held_not_executed(self):
        with patch.object(self.orch.tool_manager, "execute_tool") as ex:
            results = self.orch._execute_tool_calls(
                self._call("run_powershell", {"script": "Get-Process"}))
        ex.assert_not_called()
        self.assertTrue(results[0]["pending_confirmation"])
        self.assertFalse(results[0]["verified_success"])
        self.assertEqual(self.orch._pending_action["tool"], "run_powershell")

    def test_safe_tool_runs_without_confirmation(self):
        with patch.object(self.orch.tool_manager, "execute_tool",
                          return_value="ok") as ex:
            self.orch._execute_tool_calls(self._call("get_system_status", {}))
        ex.assert_called_once()
        self.assertIsNone(self.orch._pending_action)

    def test_yes_executes_the_held_action(self):
        self.orch._pending_action = {"tool": "run_powershell", "args": {"script": "x"}}
        with patch.object(self.orch.tool_manager, "execute_tool",
                          return_value="done") as ex:
            resp = self.orch._resolve_pending_confirmation("yes")
        ex.assert_called_once_with("run_powershell", {"script": "x"})
        self.assertIn("Confirmed", resp["action"])
        self.assertIsNone(self.orch._pending_action)

    def test_no_cancels_without_executing(self):
        self.orch._pending_action = {"tool": "delete_file", "args": {"path": "x"}}
        with patch.object(self.orch.tool_manager, "execute_tool") as ex:
            resp = self.orch._resolve_pending_confirmation("no")
        ex.assert_not_called()
        self.assertIn("Cancelled", resp["action"])
        self.assertIsNone(self.orch._pending_action)

    def test_unrelated_command_drops_stale_pending_action(self):
        """A later stray 'yes' must not fire an action the user moved on from."""
        self.orch._pending_action = {"tool": "delete_file", "args": {"path": "x"}}
        with patch.object(self.orch.tool_manager, "execute_tool") as ex:
            resp = self.orch._resolve_pending_confirmation("what's the weather")
        ex.assert_not_called()
        self.assertIsNone(resp, "Unrelated text must fall through to normal handling")
        self.assertIsNone(self.orch._pending_action)

    def test_full_autonomy_bypasses_the_gate(self):
        self.orch.autonomy = "full"
        self.assertFalse(self.orch._should_confirm("run_powershell"))

    def test_both_paths_share_one_danger_definition(self):
        """The gate and the ReAct loop must never disagree about a tool."""
        loop = self.orch._get_agentic_loop()
        for name in ("run_powershell", "execute_terminal", "delete_file",
                     "kill_process", "send_email", "get_system_status",
                     "take_screenshot", "list_files"):
            with self.subTest(tool=name):
                self.assertEqual(self.orch._should_confirm(name), loop._is_dangerous(name),
                                 f"paths disagree on {name}")


class TestFastPath(unittest.TestCase):
    """Fast-path regexes must resolve to the right tool -- without executing it."""

    @classmethod
    def setUpClass(cls):
        cls.orch = OSKernel().orchestrator

    def _route(self, text):
        """Return (tool_name, args) the fast path would call, executing nothing."""
        calls = []

        def _capture(name, args=None):
            calls.append((name, args))
            return {"success": True}

        with patch.object(self.orch.tool_manager, "execute_tool", side_effect=_capture):
            result = self.orch._check_fast_path(text)
        return (calls[0] if calls else (None, None)), result

    def test_open_known_website(self):
        (tool, args), result = self._route("open youtube")
        self.assertEqual(tool, "open_website")
        self.assertIn("youtube.com", args["url"])
        self.assertTrue(result["success"])

    def test_open_website_tolerates_filler_words(self):
        for phrasing in ("please open github", "hey jarvis open github", "open github."):
            with self.subTest(phrasing=phrasing):
                (tool, args), _ = self._route(phrasing)
                self.assertEqual(tool, "open_website", "failed on %r" % phrasing)
                self.assertIn("github.com", args["url"])

    def test_unknown_command_falls_through(self):
        (tool, _), result = self._route("what is the meaning of life")
        self.assertIsNone(tool, "Open-ended question must not hit the fast path")
        self.assertIsNone(result)


if __name__ == "__main__":
    print("=" * 62)
    print("J.A.R.V.I.S. AI OS -- MASTER SYSTEM INTEGRITY TEST")
    print("=" * 62)
    unittest.main(verbosity=2)
