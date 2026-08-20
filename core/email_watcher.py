"""
J.A.R.V.I.S. Email Watcher
Background daemon that polls the inbox via IMAP for new mail and proactively
announces important ones through voice + Telegram, the same way
core/whatsapp_watcher.py handles WhatsApp notifications.

Uses BODY.PEEK[] fetches exclusively — checking for new mail never marks the
user's real inbox messages as read.

Setup: uses the same JARVIS_EMAIL_ADDRESS / JARVIS_EMAIL_PASSWORD credentials
as plugins/email_client.py (Gmail: use an App Password).
"""

import os
import time
import threading
import logging
from email.header import decode_header
from typing import Dict, List, Optional
from dataclasses import dataclass

import imaplib
import email as email_lib

logger = logging.getLogger("jarvis.email_watcher")

POLL_INTERVAL_SECONDS = int(os.environ.get("JARVIS_EMAIL_POLL_INTERVAL", "60"))
COOLDOWN_PER_SENDER_SECONDS = 120

_PROMO_SENDER_MARKERS = (
    "noreply", "no-reply", "notifications@", "newsletter", "mailer-daemon",
    "donotreply", "do-not-reply",
)


def _decode_subject(raw_subject) -> str:
    if raw_subject is None:
        return "(No Subject)"
    try:
        parts = decode_header(raw_subject)
        out = []
        for data, charset in parts:
            if isinstance(data, bytes):
                out.append(data.decode(charset or "utf-8", errors="ignore"))
            else:
                out.append(str(data))
        return " ".join(out)
    except Exception:
        return str(raw_subject)


@dataclass
class InboxMessage:
    uid: bytes
    sender: str
    subject: str
    snippet: str


class EmailWatcher:
    """Background daemon that announces new important inbox mail."""

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_seen_uid = 0
        self._announced_senders: Dict[str, float] = {}

    # ── Config (lazy import — reuses plugins/email_client's account setup) ──

    def _config(self):
        from plugins.email_client import EMAIL_ADDRESS, EMAIL_PASSWORD, IMAP_SERVER
        return EMAIL_ADDRESS, EMAIL_PASSWORD, IMAP_SERVER

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        address, password, _ = self._config()
        if not address or not password:
            logger.info("[EmailWatcher] Email not configured — skipping.")
            return

        self._running = True
        self._initialize_watermark()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="email-watcher")
        self._thread.start()
        logger.info("[EmailWatcher] Started. Polling every %ds.", POLL_INTERVAL_SECONDS)
        print(f"[JARVIS] Email Watcher started (polling every {POLL_INTERVAL_SECONDS}s).")

    def stop(self):
        self._running = False

    # ── IMAP helpers ─────────────────────────────────────────────

    def _connect(self):
        address, password, imap_server = self._config()
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(address, password)
        mail.select("INBOX")
        return mail

    def _initialize_watermark(self):
        """Skip announcing pre-existing unread mail on first start."""
        try:
            mail = self._connect()
            _, data = mail.uid("search", None, "ALL")
            mail.logout()
            uids = data[0].split()
            if uids:
                self._last_seen_uid = int(uids[-1])
                logger.info("[EmailWatcher] Initialized watermark to UID %d", self._last_seen_uid)
        except Exception as e:
            logger.warning("[EmailWatcher] Watermark init failed: %s", e)

    def _fetch_new(self) -> List[InboxMessage]:
        mail = self._connect()
        try:
            _, data = mail.uid("search", None, "ALL")
            uids = [int(u) for u in data[0].split() if int(u) > self._last_seen_uid]
            if not uids:
                return []
            self._last_seen_uid = max(uids)

            messages = []
            for uid in uids:
                # BODY.PEEK never sets the \Seen flag — the user's inbox is untouched.
                _, msg_data = mail.uid(
                    "fetch", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])"
                )
                if not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                sender = msg.get("From", "Unknown")
                subject = _decode_subject(msg.get("Subject"))
                messages.append(InboxMessage(uid=uid, sender=sender, subject=subject, snippet=""))
            return messages
        finally:
            mail.logout()

    # ── Importance classification (mirrors whatsapp_watcher's approach) ──

    def _classify_important(self, messages: List[InboxMessage]) -> List[InboxMessage]:
        important = []
        for msg in messages:
            sender_lower = msg.sender.lower()
            if any(marker in sender_lower for marker in _PROMO_SENDER_MARKERS):
                continue

            try:
                from core.llm_provider import llm_generate
                prompt = (
                    "You are classifying an email for importance to decide whether to "
                    "interrupt the user with a voice notification.\n"
                    f"From: {msg.sender}\nSubject: {msg.subject}\n\n"
                    "Reply with EXACTLY one word: URGENT or IGNORE.\n"
                    "URGENT = a real message from a person or service needing attention "
                    "(work, personal, security, bills, deliveries).\n"
                    "IGNORE = marketing, promotions, social media digests, spam."
                )
                result = llm_generate(prompt, temperature=0.0, max_tokens=10, timeout=10)
                if "URGENT" in result.upper():
                    important.append(msg)
                else:
                    logger.debug("[EmailWatcher] Classified as IGNORE: %s", msg.subject)
            except Exception as e:
                logger.debug("[EmailWatcher] LLM classification failed, including: %s", e)
                important.append(msg)
        return important

    # ── Announcement ─────────────────────────────────────────────

    def _announce(self, messages: List[InboxMessage]):
        if not messages:
            return

        now = time.time()
        fresh = []
        for msg in messages:
            last = self._announced_senders.get(msg.sender, 0)
            if now - last > COOLDOWN_PER_SENDER_SECONDS:
                fresh.append(msg)
                self._announced_senders[msg.sender] = now
        if not fresh:
            return

        if len(fresh) == 1:
            m = fresh[0]
            text = f"Sir, you've received an email from {m.sender}: '{m.subject}'"
        else:
            senders = list({m.sender for m in fresh})
            sender_list = senders[0] if len(senders) == 1 else f"{', '.join(senders[:-1])} and {senders[-1]}"
            text = f"Sir, you have {len(fresh)} new emails, including from {sender_list}."

        logger.info("[EmailWatcher] Announcing: %s", text)
        self._speak(text)
        self._push_telegram(text)

    def _speak(self, text: str):
        try:
            from core.voice_pipeline import PipelineState
            from ui.web_server import _get_pipeline
            pipeline = _get_pipeline()
            if not pipeline:
                return
            if pipeline.state in (PipelineState.SPEAKING, PipelineState.LISTENING, PipelineState.PROCESSING):
                return  # Don't interrupt; Telegram push still lands.
            if pipeline.on_response:
                pipeline.on_response(text)
            pipeline._set_state(PipelineState.SPEAKING)
            pipeline.tts.speak(text)
        except Exception as e:
            logger.debug("[EmailWatcher] Voice announce skipped: %s", e)

    def _push_telegram(self, text: str):
        try:
            from core.telegram_bridge import _telegram_bridge
            _telegram_bridge.send_notification(f"📧 {text}")
        except Exception:
            pass

    # ── Main loop ────────────────────────────────────────────────

    def _poll_loop(self):
        while self._running:
            try:
                new_msgs = self._fetch_new()
                if new_msgs:
                    important = self._classify_important(new_msgs)
                    self._announce(important)
            except imaplib.IMAP4.error as e:
                logger.warning("[EmailWatcher] IMAP error: %s", e)
            except Exception as e:
                logger.error("[EmailWatcher] Poll error: %s", e)
            time.sleep(POLL_INTERVAL_SECONDS)


_watcher = EmailWatcher()


def get_email_watcher() -> EmailWatcher:
    return _watcher
