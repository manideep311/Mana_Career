"""Account email wording and links (no DB)."""

from app.domain.auth.account_emails import link_for, reset_email, verify_email
from app.domain.auth.tokens import hash_link_token, new_link_token


def test_links_carry_the_token_in_the_fragment():
    assert link_for("https://career.example", "password_reset", "abc") == (
        "https://career.example/reset-password#token=abc"
    )
    assert link_for("http://localhost:3000", "email_verify", "xyz") == (
        "http://localhost:3000/verify-email#token=xyz"
    )


def test_reset_email_says_what_happened_when_it_expires_and_how_to_ignore_it():
    msg = reset_email(
        name="Asha Rao", email="asha@example.com",
        link="https://career.example/reset-password#token=abc", brand="Mana Career",
    )
    assert msg.to_email == "asha@example.com" and msg.to_name == "Asha Rao"
    assert msg.subject == "Reset your Mana Career password"
    assert msg.body.startswith("Hi Asha,")
    assert "https://career.example/reset-password#token=abc" in msg.body
    assert "expires in 30 minutes" in msg.body
    assert "ignore this email" in msg.body
    assert msg.from_name == "Mana Career" and msg.bcc == () and msg.reply_to is None


def test_verify_email_explains_why_it_matters():
    msg = verify_email(
        name="", email="asha@example.com",
        link="https://career.example/verify-email#token=xyz", brand="Mana Career",
    )
    assert msg.subject == "Confirm your email for Mana Career"
    assert msg.body.startswith("Hi,")
    assert "verify-email#token=xyz" in msg.body
    assert "48 hours" in msg.body
    assert "send applications" in msg.body


def test_link_tokens_are_random_and_only_their_hash_is_kept():
    raw1, h1 = new_link_token()
    raw2, _ = new_link_token()
    assert raw1 != raw2 and len(raw1) >= 40
    assert h1 == hash_link_token(raw1) and len(h1) == 64 and raw1 not in h1
