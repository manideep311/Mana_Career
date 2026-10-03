import pytest

from app.domain.email.mime import InvalidEmailMessage, build_mime, recipients_of
from app.domain.email.types import EmailAttachment, EmailMessage

PDF = EmailAttachment("Asha Rao - Resume.pdf", "application/pdf", b"%PDF-1.4 test")


def _message(**over: object) -> EmailMessage:
    base: dict[str, object] = {
        "to_email": "hiring@acme.test",
        "to_name": "Hiring Team",
        "subject": "Application: Backend Engineer",
        "body": "Hello,\n\nPlease find my application attached.",
        "from_name": "Asha Rao via Mana Career",
        "reply_to": "asha@example.com",
        "bcc": ("asha@example.com",),
        "attachments": (PDF,),
    }
    base.update(over)
    return EmailMessage(**base)  # type: ignore[arg-type]


def test_headers_name_the_sender_and_route_replies_to_the_applicant():
    mime = build_mime(_message(), from_address="applications@mana.test")
    assert mime["From"] == "Asha Rao via Mana Career <applications@mana.test>"
    assert mime["To"] == "Hiring Team <hiring@acme.test>"
    assert mime["Reply-To"] == "asha@example.com"
    assert mime["Subject"] == "Application: Backend Engineer"
    assert mime["Message-ID"].endswith("@mana.test>")
    assert mime["Date"]


def test_bcc_is_delivered_but_never_shown_in_headers():
    message = _message()
    mime = build_mime(message, from_address="applications@mana.test")
    assert "Bcc" not in mime
    assert recipients_of(message) == ["hiring@acme.test", "asha@example.com"]


def test_body_and_attachment_travel_together():
    mime = build_mime(_message(), from_address="applications@mana.test")
    parts = list(mime.iter_attachments())
    assert [p.get_filename() for p in parts] == ["Asha Rao - Resume.pdf"]
    assert parts[0].get_content_type() == "application/pdf"
    assert parts[0].get_content() == b"%PDF-1.4 test"
    body = mime.get_body(preferencelist=("plain",))
    assert body is not None and "Please find my application" in body.get_content()


def test_plain_message_without_attachments_or_name():
    mime = build_mime(
        _message(to_name=None, attachments=(), bcc=(), reply_to=None, from_name=None),
        from_address="applications@mana.test",
    )
    assert mime["To"] == "hiring@acme.test"
    assert mime["From"] == "applications@mana.test"
    assert "Reply-To" not in mime
    assert not list(mime.iter_attachments())


@pytest.mark.parametrize(
    "field",
    ["subject", "to_name", "from_name", "to_email", "reply_to"],
)
def test_header_injection_is_refused(field: str):
    with pytest.raises(InvalidEmailMessage):
        build_mime(
            _message(**{field: "x@y.test\r\nBcc: victim@evil.test"}),
            from_address="applications@mana.test",
        )


def test_invalid_recipient_addresses_are_refused():
    with pytest.raises(InvalidEmailMessage):
        build_mime(_message(to_email="not an address"), from_address="applications@mana.test")
    with pytest.raises(InvalidEmailMessage):
        build_mime(_message(bcc=("bad",)), from_address="applications@mana.test")
