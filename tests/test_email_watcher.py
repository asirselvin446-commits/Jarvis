"""
Tests for core.email_watcher — proactive new-mail notification daemon.
No real IMAP/SMTP calls — everything is faked.
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.email_watcher as ew


class TestSubjectDecoding:
    def test_none_subject(self):
        assert ew._decode_subject(None) == "(No Subject)"

    def test_plain_subject(self):
        assert ew._decode_subject("Hello there") == "Hello there"


class TestStartupGuard:
    def test_skips_when_unconfigured(self, monkeypatch):
        watcher = ew.EmailWatcher()
        monkeypatch.setattr(watcher, "_config", lambda: ("", "", ""))
        watcher.start()
        assert watcher._running is False


class TestImportanceClassification:
    def test_promo_sender_always_ignored(self, monkeypatch):
        watcher = ew.EmailWatcher()
        msgs = [ew.InboxMessage(uid=1, sender="noreply@shop.com", subject="50% off!", snippet="")]
        out = watcher._classify_important(msgs)
        assert out == []

    def test_real_sender_uses_llm(self, monkeypatch):
        watcher = ew.EmailWatcher()
        msgs = [ew.InboxMessage(uid=1, sender="boss@work.com", subject="Meeting moved", snippet="")]

        import core.llm_provider as lp
        monkeypatch.setattr(lp, "llm_generate", lambda *a, **k: "URGENT")
        out = watcher._classify_important(msgs)
        assert len(out) == 1

    def test_llm_ignore_filters_out(self, monkeypatch):
        watcher = ew.EmailWatcher()
        msgs = [ew.InboxMessage(uid=1, sender="digest@social.com", subject="Weekly digest", snippet="")]

        import core.llm_provider as lp
        monkeypatch.setattr(lp, "llm_generate", lambda *a, **k: "IGNORE")
        out = watcher._classify_important(msgs)
        assert out == []


class TestAnnounceCooldown:
    def test_same_sender_not_announced_twice_quickly(self, monkeypatch):
        watcher = ew.EmailWatcher()
        calls = []
        monkeypatch.setattr(watcher, "_speak", lambda text: calls.append(text))
        monkeypatch.setattr(watcher, "_push_telegram", lambda text: None)

        msg = ew.InboxMessage(uid=1, sender="a@b.com", subject="Hi", snippet="")
        watcher._announce([msg])
        watcher._announce([msg])
        assert len(calls) == 1


class TestFetchNewUsesPeek:
    def test_fetch_uses_body_peek_not_rfc822(self, monkeypatch):
        """Checking mail must never mark the user's real inbox as read."""
        watcher = ew.EmailWatcher()
        monkeypatch.setattr(watcher, "_config", lambda: ("a@b.com", "pw", "imap.gmail.com"))

        fetch_calls = []

        class FakeMail:
            def uid(self, cmd, _, *args):
                if cmd == "search":
                    return "OK", [b"1 2 3"]
                if cmd == "fetch":
                    fetch_calls.append(args)
                    return "OK", [(b"1", b"From: a@b.com\r\nSubject: Hi\r\n\r\n")]
                return "OK", [None]

            def logout(self):
                pass

        watcher._last_seen_uid = 2
        monkeypatch.setattr(watcher, "_connect", lambda: FakeMail())
        watcher._fetch_new()

        assert any("PEEK" in str(a) for a in fetch_calls)
        assert not any("RFC822" in str(a) for a in fetch_calls)
