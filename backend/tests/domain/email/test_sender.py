from typing import ClassVar

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


def test_unknown_email_providers_are_rejected_at_startup():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+asyncpg://x", database_url_test="postgresql+asyncpg://x",
            redis_url="redis://x", jwt_secret="x", email_provider="sendgrid",
        )


async def test_console_sender_returns_a_synthetic_message_id():
    sender = ConsoleEmailSender()
    result = await sender.send(
        EmailMessage(to_email="a@b.com", to_name="A", subject="Hi", body="Hello")
    )
    assert result.provider == "console"
    assert result.provider_message_id.startswith("console-")


# --------------------------------------------------------------------- SMTP


def _smtp_settings(**over: object):
    from app.core.config import Settings

    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://x", "database_url_test": "postgresql+asyncpg://x",
        "redis_url": "redis://x", "jwt_secret": "x", "email_provider": "smtp",
        "smtp_host": "smtp.example.com", "smtp_username": "user", "smtp_password": "app-pass",
        "email_from_address": "applications@mana.test",
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


class _FakeSMTP:
    instances: ClassVar[list["_FakeSMTP"]] = []
    fail_with: ClassVar[Exception | None] = None

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list[str] = []
        self.sent: list[tuple[object, list[str]]] = []
        _FakeSMTP.instances.append(self)

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append("quit")

    def starttls(self, context: object = None) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login:{user}:{password}")

    def send_message(self, msg: object, to_addrs: list[str]) -> dict[str, object]:
        if _FakeSMTP.fail_with is not None:
            raise _FakeSMTP.fail_with
        self.sent.append((msg, to_addrs))
        return {}


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch):
    import smtplib

    _FakeSMTP.instances = []
    _FakeSMTP.fail_with = None
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
    return _FakeSMTP


def test_factory_returns_the_smtp_sender_when_configured():
    from app.domain.email.smtp import SmtpEmailSender

    assert isinstance(get_email_sender(_smtp_settings()), SmtpEmailSender)


async def test_smtp_sender_upgrades_to_tls_logs_in_and_sends(fake_smtp):
    from app.domain.email.smtp import SmtpEmailSender

    result = await SmtpEmailSender(_smtp_settings()).send(
        EmailMessage(
            to_email="hiring@acme.test", to_name="Hiring", subject="Hi", body="Hello",
            bcc=("me@example.com",),
        )
    )
    conn = fake_smtp.instances[0]
    assert (conn.host, conn.port) == ("smtp.example.com", 587)
    assert conn.calls[:2] == ["starttls", "login:user:app-pass"]
    msg, to_addrs = conn.sent[0]
    assert to_addrs == ["hiring@acme.test", "me@example.com"]
    assert result.provider == "smtp"
    assert result.provider_message_id == msg["Message-ID"]  # type: ignore[index]


async def test_unauthenticated_local_server_skips_tls_and_login(fake_smtp):
    from app.domain.email.smtp import SmtpEmailSender

    settings = _smtp_settings(
        smtp_security="none", smtp_username=None, smtp_password=None, smtp_port=1025
    )
    await SmtpEmailSender(settings).send(
        EmailMessage(to_email="a@b.test", to_name=None, subject="Hi", body="Hello")
    )
    assert fake_smtp.instances[0].calls == ["quit"]


async def test_smtp_failures_become_a_safe_delivery_error(fake_smtp):
    import smtplib

    from app.domain.email.smtp import EmailDeliveryError, SmtpEmailSender

    fake_smtp.fail_with = smtplib.SMTPRecipientsRefused({"a@b.test": (550, b"no such user")})
    with pytest.raises(EmailDeliveryError) as exc:
        await SmtpEmailSender(_smtp_settings()).send(
            EmailMessage(to_email="a@b.test", to_name=None, subject="Hi", body="Hello")
        )
    assert "app-pass" not in str(exc.value)
    assert "rejected" in str(exc.value).lower()
