from __future__ import annotations

from app.core.config import Settings
from app.domain.email.sender import ConsoleEmailSender, EmailSender


def get_email_sender(settings: Settings) -> EmailSender:
    # EMAIL_PROVIDER only accepts "console": nothing is sent outside the app.
    return ConsoleEmailSender()
