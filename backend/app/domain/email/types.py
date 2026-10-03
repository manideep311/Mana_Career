from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class EmailMessage:
    to_email: str
    to_name: str | None
    subject: str
    body: str
    body_format: str = "plain"
    # Display name only; the address always comes from EMAIL_FROM_ADDRESS so a
    # message can never claim to be from someone else's domain.
    from_name: str | None = None
    reply_to: str | None = None
    bcc: tuple[str, ...] = ()
    attachments: tuple[EmailAttachment, ...] = ()


@dataclass(frozen=True)
class EmailSendResult:
    provider: str
    provider_message_id: str
