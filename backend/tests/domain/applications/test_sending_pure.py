"""How an approved application email is addressed: redirect vs live (no DB)."""

from app.domain.applications.sending import REDIRECT_NOTE, compose_message, resume_filename
from app.domain.email.types import EmailAttachment

PDF = EmailAttachment("Asha Rao - Resume.pdf", "application/pdf", b"%PDF")


def _compose(delivery: str, **over: object):
    args: dict[str, object] = {
        "applicant_name": "Asha Rao",
        "applicant_email": "asha@example.com",
        "to_email": "hiring@acme.test",
        "to_name": "Hiring Team",
        "subject": "Application: Backend Engineer",
        "body": "Hello, please find my application attached.",
        "body_format": "plain",
        "brand": "Mana Career",
        "delivery": delivery,
        "attachment": PDF,
    }
    args.update(over)
    return compose_message(**args)  # type: ignore[arg-type]


def test_redirect_delivers_to_the_applicant_and_names_the_real_recipient():
    message, delivered_to = _compose("redirect")
    assert delivered_to == "asha@example.com"
    assert message.to_email == "asha@example.com"
    assert message.bcc == ()  # they are the recipient already
    assert message.body.startswith(
        REDIRECT_NOTE.format(who="Hiring Team <hiring@acme.test>")
    )
    assert message.body.endswith("Hello, please find my application attached.")
    assert message.subject == "Application: Backend Engineer"  # unchanged


def test_live_delivers_to_the_employer_with_a_copy_to_the_applicant():
    message, delivered_to = _compose("live")
    assert delivered_to == "hiring@acme.test"
    assert (message.to_email, message.to_name) == ("hiring@acme.test", "Hiring Team")
    assert message.bcc == ("asha@example.com",)
    assert message.body == "Hello, please find my application attached."


def test_replies_always_reach_the_applicant_and_the_sender_is_labelled():
    for delivery in ("redirect", "live"):
        message, _ = _compose(delivery)
        assert message.reply_to == "asha@example.com"
        assert message.from_name == "Asha Rao via Mana Career"
        assert message.attachments == (PDF,)


def test_no_self_copy_when_the_applicant_sends_to_themselves():
    message, _ = _compose("live", to_email="ASHA@example.com")
    assert message.bcc == ()


def test_missing_name_and_attachment_are_handled():
    message, _ = _compose("redirect", applicant_name="", to_name=None, attachment=None)
    assert message.from_name == "Mana Career"
    assert message.attachments == ()
    assert "hiring@acme.test" in message.body.splitlines()[0]


def test_resume_filename_is_safe():
    assert resume_filename("Asha Rao") == "Asha Rao - Resume.pdf"
    assert resume_filename("A/B\C:<x>") == "ABCx - Resume.pdf"
    assert resume_filename("  ") == "Resume.pdf"
