"""
Tests for the Anthropic Claude provider integration in core.llm_provider.
No network calls — the Anthropic client is faked.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.llm_provider as lp


class TestMessageConversion:
    def test_system_extracted_and_first_is_user(self):
        system, conv = lp._convert_messages_to_anthropic([
            {"role": "system", "content": "You are Jarvis."},
            {"role": "assistant", "content": "hi"},  # first non-system is assistant
        ])
        assert system == "You are Jarvis."
        assert conv[0]["role"] == "user"  # a synthetic user turn is prepended

    def test_roles_mapped(self):
        _, conv = lp._convert_messages_to_anthropic([
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ])
        assert [m["role"] for m in conv] == ["user", "assistant"]


class TestToolConversion:
    def test_openai_to_anthropic_shape(self):
        out = lp._convert_tools_to_anthropic([
            {"type": "function", "function": {
                "name": "open_app", "description": "opens",
                "parameters": {"type": "object", "properties": {}}}}
        ])
        assert out[0]["name"] == "open_app"
        assert "input_schema" in out[0]
        assert "parameters" not in out[0]

    def test_none_tools(self):
        assert lp._convert_tools_to_anthropic(None) is None


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeResp:
    content = [
        _Block(type="text", text="Building. "),
        _Block(type="tool_use", name="write_code_file", input={"path": "a.py"}),
    ]


class _FakeClient:
    def with_options(self, **kw):
        return self

    class messages:
        @staticmethod
        def create(**kw):
            return _FakeResp()


class TestAnthropicChat:
    def test_parses_text_and_tool_use(self, monkeypatch):
        monkeypatch.setattr(lp, "_anthropic_client", _FakeClient())
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        r = lp._anthropic_chat([{"role": "user", "content": "build"}],
                               tools=[{"function": {"name": "write_code_file", "parameters": {}}}])
        assert r["content"].strip() == "Building."
        assert r["tool_calls"][0]["function"]["name"] == "write_code_file"
        assert r["tool_calls"][0]["function"]["arguments"] == {"path": "a.py"}

    def test_llm_chat_prefers_claude(self, monkeypatch):
        monkeypatch.setattr(lp, "_anthropic_client", _FakeClient())
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        r = lp.llm_chat([{"role": "user", "content": "build"}], prefer="anthropic")
        assert "tool_calls" in r

    def test_llm_chat_ignores_claude_without_preference(self, monkeypatch):
        # No prefer and PREFER_CLAUDE off -> Claude is not used even if key present.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(lp, "PREFER_CLAUDE", False)
        called = {"claude": False}

        def spy(*a, **k):
            called["claude"] = True
            return {"content": "x"}

        monkeypatch.setattr(lp, "_anthropic_chat", spy)
        # Force all other providers to be absent so it returns the fallback msg.
        monkeypatch.setattr(lp, "_get_api_key", lambda: None)
        monkeypatch.setattr(lp, "_get_groq_api_key", lambda: None)
        monkeypatch.setattr(lp, "_get_openrouter_api_key", lambda: None)
        monkeypatch.setattr(lp, "PREFER_CLOUD_ONLY", True)
        lp.llm_chat([{"role": "user", "content": "hi"}])
        assert called["claude"] is False
