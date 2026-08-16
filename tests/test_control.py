"""
Tests for the runtime control plane: emergency stop + audit log.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.control import ControlPlane, _redact


class TestRedaction:
    def test_secret_keys_redacted(self):
        r = _redact({"query": "cats", "api_key": "sk-123", "token": "abc",
                     "nested": {"password": "p", "ok": "v"}})
        assert r["query"] == "cats"
        assert r["api_key"] == "***REDACTED***"
        assert r["token"] == "***REDACTED***"
        assert r["nested"]["password"] == "***REDACTED***"
        assert r["nested"]["ok"] == "v"

    def test_long_strings_truncated(self):
        out = _redact({"blob": "x" * 1000})
        assert out["blob"].endswith("…") and len(out["blob"]) < 1000


class TestEmergencyStop:
    def test_stop_and_clear(self):
        cp = ControlPlane()
        assert cp.is_stopped() is False
        cp.request_stop("test")
        assert cp.is_stopped() is True
        cp.clear_stop()
        assert cp.is_stopped() is False


class TestAuditLog:
    def test_audit_writes_and_redacts(self, tmp_path):
        cp = ControlPlane()
        cp._audit_path = str(tmp_path / "audit.jsonl")
        cp.audit("open_website", {"url": "https://x.com", "token": "secret"}, "ok")
        records = cp.tail_audit(5)
        assert len(records) == 1
        assert records[0]["tool"] == "open_website"
        assert records[0]["args"]["token"] == "***REDACTED***"
        assert records[0]["args"]["url"] == "https://x.com"
        assert records[0]["status"] == "ok"

    def test_tail_missing_file_returns_empty(self, tmp_path):
        cp = ControlPlane()
        cp._audit_path = str(tmp_path / "nope.jsonl")
        assert cp.tail_audit() == []


class TestAgenticStopIntegration:
    def test_stop_flag_halts_loop(self, monkeypatch):
        import core.agentic_loop as al
        monkeypatch.setattr(al.time, "sleep", lambda *a, **k: None)
        from core.control import get_control_plane

        cp = get_control_plane()
        cp.clear_stop()

        class Reg:
            def __init__(self):
                self.calls = []

            def get_tool_schemas_for_llm(self):
                return []

            def get_meta(self, n):
                return {}

            def execute(self, n, a):
                self.calls.append(n)
                cp.request_stop("test")  # user hits stop after first tool
                return "ok"

        step = {"content": "", "tool_calls": [{"function": {"name": "t", "arguments": {}}}]}
        monkeypatch.setattr(al, "llm_chat", lambda *a, **k: step)

        reg = Reg()
        res = al.ReActLoop(max_iterations=10, registry=reg).run("long task")
        cp.clear_stop()

        assert res.success is False
        assert "Stopped" in res.response
        assert len(reg.calls) <= 2  # halted quickly, did not run all 10 steps
