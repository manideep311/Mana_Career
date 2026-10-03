"""Turn an ``EmailMessage`` into a standards-compliant MIME message.

Pure and provider-neutral. Every header value is checked for CR/LF (header
injection) and every address for a sane shape before anything is built, so a
recipient typed into the review card can never smuggle in extra headers.
"""

from __future__ import annotations

import email.policy
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, formatdate, make_msgid

from app.core.config import EMAIL_ADDRESS_RE
from app.domain.email.types import EmailMessage


class InvalidEmailMessage(ValueError):
    """The message can't be sent as written (bad address or header value)."""


def _header(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if "\r" in value or "\n" in value:
        raise InvalidEmailMessage(f"{field} can't contain line breaks")
    return value.strip() or None


def _address(value: str, field: str) -> str:
    cleaned = _header(value, field) or ""
    if not EMAIL_ADDRESS_RE.match(cleaned):
        raise InvalidEmailMessage(f"{field} isn't a valid email address")
    return cleaned


def recipients_of(message: EmailMessage) -> list[str]:
    """Envelope recipients: To plus Bcc (Bcc never appears in the headers)."""
    to = _address(message.to_email, "Recipient")
    return [to, *(_address(b, "Copy recipient") for b in message.bcc)]


def build_mime(message: EmailMessage, *, from_address: str) -> MimeMessage:
    sender = _address(from_address, "Sender address")
    to = _address(message.to_email, "Recipient")
    recipients_of(message)  # validates Bcc addresses too
    to_name = _header(message.to_name, "Recipient name")
    from_name = _header(message.from_name, "Sender name")
    subject = _header(message.subject, "Subject") or ""
    reply_to = _address(message.reply_to, "Reply-To") if message.reply_to else None

    mime = MimeMessage(policy=email.policy.SMTP)
    mime["From"] = formataddr((from_name, sender)) if from_name else sender
    mime["To"] = formataddr((to_name, to)) if to_name else to
    if reply_to:
        mime["Reply-To"] = reply_to
    mime["Subject"] = subject
    mime["Date"] = formatdate(localtime=False, usegmt=True)
    mime["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[1])
    subtype = "html" if message.body_format == "html" else "plain"
    mime.set_content(message.body, subtype=subtype)
    for att in message.attachments:
        maintype, _, sub = att.content_type.partition("/")
        mime.add_attachment(
            att.data,
            maintype=maintype or "application",
            subtype=sub or "octet-stream",
            filename=_header(att.filename, "Attachment name") or "attachment",
        )
    return mime
