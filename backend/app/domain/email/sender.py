from __future__ import annotations

import uuid
from typing import Protocol

from app.core.logging import get_logger
from app.domain.email.types import EmailMessage, EmailSendResult

log = get_logger("email")


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> EmailSendResult: ...


class ConsoleEmailSender:
    """Sandboxed default -- logs the message, sends nothing over the network."""

    async def send(self, message: EmailMessage) -> EmailSendResult:
        log.info(
            "email_send_console",
            to_email=message.to_email,
            subject=message.subject,
            body_len=len(message.body),
        )
        return EmailSendResult(
            provider="console", provider_message_id=f"console-{uuid.uuid4().hex}"
        )
