from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailMessage:
    to_email: str
    to_name: str | None
    subject: str
    body: str
    body_format: str = "plain"


@dataclass(frozen=True)
class EmailSendResult:
    provider: str
    provider_message_id: str
