"""
Tests for plugins.claude_builder — the Claude Code CLI build engine.
No real CLI calls: subprocess and file discovery are faked.
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plugins.claude_builder as cb


class TestHelpers:
    def test_safe_name(self):
        assert cb._safe_name("My Cool App!!") == "my-cool-app"
        assert cb._safe_name("") == "project"
        assert cb._safe_name("   ") == "project"

    def test_find_claude_present(self, monkeypatch):
        monkeypatch.setattr(cb.shutil, "which", lambda c: "C:/npm/claude.cmd" if c == "claude" else None)
        assert cb._find_claude() == "C:/npm/claude.cmd"

    def test_find_claude_absent(self, monkeypatch):
        monkeypatch.setattr(cb.shutil, "which", lambda c: None)
        monkeypatch.setattr(cb.os.path, "exists", lambda p: False)
        assert cb._find_claude() is None


class TestBuildGuards:
    def test_not_installed_message(self, monkeypatch):
        monkeypatch.setattr(cb, "_find_claude", lambda: None)
        out = cb.build_with_claude("a clock", "clock")
        assert "not installed" in out.lower()

    def test_empty_request(self, monkeypatch):
        monkeypatch.setattr(cb, "_find_claude", lambda: "claude")
        out = cb.build_with_claude("   ", "clock")
        assert "empty" in out.lower()


class TestBuildRun:
    def _fake_completed(self, stdout="Created index.html", stderr=""):
        return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=0)

    def test_reports_created_files(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cb, "_find_claude", lambda: "claude")
        monkeypatch.setattr(cb, "_PROJECTS_ROOT", str(tmp_path))
        monkeypatch.setattr(cb.webbrowser, "open", lambda *a, **k: True)

        def fake_run(cmd, **kw):
            # Simulate Claude writing a file into the project dir.
            proj = kw["cwd"]
            with open(os.path.join(proj, "index.html"), "w") as f:
                f.write("<!DOCTYPE html><html></html>")
            return self._fake_completed()

        monkeypatch.setattr(cb.subprocess, "run", fake_run)
        out = cb.build_with_claude("a clock", "clock")
        assert "Built 'clock'" in out
        assert "index.html" in out

    def test_honest_when_no_files(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cb, "_find_claude", lambda: "claude")
        monkeypatch.setattr(cb, "_PROJECTS_ROOT", str(tmp_path))
        monkeypatch.setattr(cb.subprocess, "run",
                            lambda cmd, **kw: self._fake_completed(stdout="I couldn't."))
        out = cb.build_with_claude("a clock", "clock")
        assert "no new files" in out.lower()
