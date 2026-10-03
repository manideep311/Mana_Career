"""Real SMTP round trip against Mailpit -- runs in CI (service container).

Locally it skips unless MAILPIT_URL is set, e.g. after
`docker compose up mailpit` with MAILPIT_URL=http://localhost:8025.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import httpx
import pytest

from app.core.config import Settings
from app.domain.email.smtp import SmtpEmailSender
from app.domain.email.types import EmailAttachment, EmailMessage

MAILPIT_URL = os.environ.get("MAILPIT_URL")

pytestmark = pytest.mark.skipif(
    not MAILPIT_URL, reason="needs a Mailpit server (set MAILPIT_URL)"
)


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://x", database_url_test="postgresql+asyncpg://x",
        redis_url="redis://x", jwt_secret="x", email_provider="smtp",
        smtp_host="localhost", smtp_port=int(os.environ.get("MAILPIT_SMTP_PORT", "1025")),
        smtp_security="none", email_from_address="applications@mana.test",
    )


async def _find(client: httpx.AsyncClient, subject: str) -> dict[str, object]:
    for _ in range(50):
        listing = (await client.get("/api/v1/search", params={"query": f'subject:"{subject}"'}))
        messages = listing.json().get("messages") or []
        if messages:
            full = await client.get(f"/api/v1/message/{messages[0]['ID']}")
            return dict(full.json())
        await asyncio.sleep(0.1)
    raise AssertionError(f"Mailpit never received {subject!r}")


async def test_an_application_email_arrives_with_headers_and_resume():
    subject = f"Application: Backend Engineer [{uuid.uuid4().hex[:8]}]"
    result = await SmtpEmailSender(_settings()).send(
        EmailMessage(
            to_email="asha@example.com", to_name="Asha Rao", subject=subject,
            body="Mana Career demo note\n\nHello, my application is attached.",
            from_name="Asha Rao via Mana Career", reply_to="asha@example.com",
            attachments=(
                EmailAttachment("Asha Rao - Resume.pdf", "application/pdf", b"%PDF-1.4 demo"),
            ),
        )
    )
    assert result.provider == "smtp"

    async with httpx.AsyncClient(base_url=MAILPIT_URL or "", timeout=10) as client:
        message = await _find(client, subject)

    assert message["From"] == {"Name": "Asha Rao via Mana Career",
                               "Address": "applications@mana.test"}
    assert message["To"] == [{"Name": "Asha Rao", "Address": "asha@example.com"}]
    assert message["ReplyTo"] == [{"Name": "", "Address": "asha@example.com"}]
    assert "my application is attached" in str(message["Text"])
    attachments = message["Attachments"]
    assert isinstance(attachments, list)
    assert [a["FileName"] for a in attachments] == ["Asha Rao - Resume.pdf"]
    assert attachments[0]["ContentType"] == "application/pdf"
