from __future__ import annotations

from app.core.config import Settings
from app.domain.email.sender import ConsoleEmailSender, EmailSender
from app.domain.email.smtp import SmtpEmailSender


def get_email_sender(settings: Settings) -> EmailSender:
    # Console unless SMTP is explicitly configured: nothing leaves the box by default.
    if settings.email_provider == "smtp":
        return SmtpEmailSender(settings)
    return ConsoleEmailSender()
