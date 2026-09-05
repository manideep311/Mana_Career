from __future__ import annotations

from app.core.config import Settings
from app.domain.email.sender import ConsoleEmailSender, EmailSender


def get_email_sender(settings: Settings) -> EmailSender:
    if settings.email_provider == "console":
        return ConsoleEmailSender()
    raise NotImplementedError(f"{settings.email_provider} email adapter lands in a later phase")
