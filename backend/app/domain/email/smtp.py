"""Deliver email through any SMTP server.

Uses the standard library in a worker thread (``smtplib`` is blocking), with a
timeout, STARTTLS or implicit TLS, and optional login. Every failure surfaces as
``EmailDeliveryError`` with a short reason that is safe to show the user: no
server banners, credentials or stack traces.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage as MimeMessage

from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.email.mime import build_mime, recipients_of
from app.domain.email.types import EmailMessage, EmailSendResult

log = get_logger("email.smtp")


class EmailDeliveryError(RuntimeError):
    """The mail server didn't accept the message. ``str()`` is user-safe."""


def _reason(exc: Exception) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "The mail server rejected the sending account's login."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "The mail server rejected the recipient address."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "The mail server rejected the sender address."
    if isinstance(exc, (TimeoutError, smtplib.SMTPServerDisconnected, ConnectionError)):
        return "The mail server didn't respond. Try again in a few minutes."
    return "The mail server couldn't accept this message."


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._host = (settings.smtp_host or "").strip()
        self._port = settings.smtp_port
        self._security = settings.smtp_security
        self._timeout = settings.smtp_timeout_seconds
        self._username = settings.smtp_username
        self._password = (
            settings.smtp_password.get_secret_value() if settings.smtp_password else None
        )
        self._from = (settings.email_from_address or "").strip()

    async def send(self, message: EmailMessage) -> EmailSendResult:
        mime = build_mime(message, from_address=self._from)
        recipients = recipients_of(message)
        try:
            await asyncio.to_thread(self._deliver, mime, recipients)
        except (smtplib.SMTPException, OSError) as exc:
            log.warning("email_send_failed", error_type=type(exc).__name__, host=self._host)
            raise EmailDeliveryError(_reason(exc)) from exc
        log.info("email_sent", recipients=len(recipients), attachments=len(message.attachments))
        return EmailSendResult(provider="smtp", provider_message_id=str(mime["Message-ID"]))

    def _deliver(self, mime: MimeMessage, recipients: list[str]) -> None:
        context = ssl.create_default_context()
        if self._security == "ssl":
            conn: smtplib.SMTP = smtplib.SMTP_SSL(
                self._host, self._port, timeout=self._timeout, context=context
            )
        else:
            conn = smtplib.SMTP(self._host, self._port, timeout=self._timeout)
        with conn:
            if self._security == "starttls":
                conn.starttls(context=context)
            if self._username:
                conn.login(self._username, self._password or "")
            conn.send_message(mime, to_addrs=recipients)
