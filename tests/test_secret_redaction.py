"""Tests that API keys never reach logs or console output.

Regression cover for a real leak: a Gemini 429 was logged as
"Cloud call failed (429 Client Error ... ?key=AIza...)", writing the key in
plaintext, because requests copies the full request URL into HTTPError text.
"""
import io
import logging
import os
import sys
import unittest

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.redaction import JarvisRedactingFormatter, redact_text

# Shaped like a real Google key but not one.
FAKE_GOOGLE_KEY = "AIzaSyBFAKEfakeFAKEfake0123456789abcdefX"
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "gemini-3.5-flash:generateContent?key=" + FAKE_GOOGLE_KEY)


def _http_error() -> requests.exceptions.HTTPError:
    return requests.exceptions.HTTPError(
        "429 Client Error: Too Many Requests for url: " + GEMINI_URL)


class TestRedactText(unittest.TestCase):

    def test_redacts_google_key_in_url(self):
        out = redact_text(str(_http_error()))
        self.assertNotIn(FAKE_GOOGLE_KEY, out)
        # Still useful for debugging: status and endpoint survive.
        self.assertIn("429", out)
        self.assertIn("generativelanguage.googleapis.com", out)

    def test_redacts_other_common_secret_shapes(self):
        for secret, text in (
            ("sk-ant-api03-abcdefghijklmnop", "Authorization: Bearer sk-ant-api03-abcdefghijklmnop"),
            ("ghp_abcdefghijklmnopqrst", "token ghp_abcdefghijklmnopqrst failed"),
        ):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, redact_text(text))

    def test_passes_through_harmless_text(self):
        msg = "Connection refused to localhost:11434"
        self.assertEqual(redact_text(msg), msg)

    def test_empty_input_is_safe(self):
        self.assertEqual(redact_text(""), "")


class TestSafeHelper(unittest.TestCase):
    """llm_provider._safe is the source-level guard on every error path."""

    def test_safe_strips_the_key(self):
        from core.llm_provider import _safe
        err = _http_error()
        self.assertIn(FAKE_GOOGLE_KEY, str(err), "test fixture should contain the key")
        self.assertNotIn(FAKE_GOOGLE_KEY, _safe(err))

    def test_error_paths_do_not_log_raw_exceptions(self):
        """Every logger call passing the exception must route through _safe."""
        import inspect
        from core import llm_provider
        src = inspect.getsource(llm_provider)
        offenders = [ln.strip() for ln in src.splitlines()
                     if "logger." in ln and ln.rstrip().endswith(", e)")]
        self.assertEqual(offenders, [], f"raw exception logged: {offenders}")


class TestFormatterBackstop(unittest.TestCase):

    def test_formatter_redacts_records(self):
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(JarvisRedactingFormatter("%(message)s"))
        log = logging.getLogger("jarvis.test.redaction")
        log.handlers[:] = [handler]
        log.propagate = False
        log.setLevel(logging.WARNING)

        log.warning("Cloud call failed (%s)", str(_http_error()))

        out = buf.getvalue()
        self.assertNotIn(FAKE_GOOGLE_KEY, out)
        self.assertIn("429", out)

    def test_install_is_idempotent(self):
        from core.redaction import install_log_redaction
        root = logging.getLogger()
        handler = logging.StreamHandler(io.StringIO())
        root.addHandler(handler)
        try:
            install_log_redaction()
            first = handler.formatter
            install_log_redaction()
            self.assertIs(handler.formatter, first, "re-wrapped an already-wrapped handler")
        finally:
            root.removeHandler(handler)


class TestNoRawKeyPrintsInVisionPaths(unittest.TestCase):
    """Modules that build ?key= URLs must not print raw exception text."""

    def test_computer_use_redacts_vision_errors(self):
        import inspect
        from plugins import computer_use
        src = inspect.getsource(computer_use._ask_vision)
        self.assertIn("redact_text", src)
        self.assertNotIn("failed ({e})", src)

    def test_vision_redacts_cloud_errors(self):
        import inspect
        from core import vision
        src = inspect.getsource(vision)
        self.assertNotIn('falling back to local", e)', src)
        self.assertIn("redact_text", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
