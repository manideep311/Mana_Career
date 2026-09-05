import pytest

from app.domain.email.factory import get_email_sender
from app.domain.email.sender import ConsoleEmailSender
from app.domain.email.types import EmailMessage


def test_get_email_sender_defaults_to_console():
    from app.core.config import Settings

    s = Settings(
        database_url="postgresql+asyncpg://x", database_url_test="postgresql+asyncpg://x",
        redis_url="redis://x", jwt_secret="x",
    )
    assert s.email_provider == "console"
    assert isinstance(get_email_sender(s), ConsoleEmailSender)


def test_get_email_sender_raises_for_unbuilt_providers():
    from app.core.config import Settings

    s = Settings(
        database_url="postgresql+asyncpg://x", database_url_test="postgresql+asyncpg://x",
        redis_url="redis://x", jwt_secret="x", email_provider="smtp",
    )
    with pytest.raises(NotImplementedError):
        get_email_sender(s)


async def test_console_sender_returns_a_synthetic_message_id():
    sender = ConsoleEmailSender()
    result = await sender.send(
        EmailMessage(to_email="a@b.com", to_name="A", subject="Hi", body="Hello")
    )
    assert result.provider == "console"
    assert result.provider_message_id.startswith("console-")
