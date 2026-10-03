"""Export serialisation and packaging (no DB)."""
from __future__ import annotations

import datetime as dt
import io
import json
import uuid
import zipfile
from decimal import Decimal

from app.domain.account.export import build_zip, serialize
from app.models.auth import AuthToken
from app.models.job import Job
from app.models.user import User


def test_serialize_keeps_content_and_drops_secrets():
    user = User(
        id=uuid.uuid4(), email="asha@example.com", password_hash="argon2-secret",
        full_name="Asha Rao", status="active", is_admin=False,
    )
    out = serialize(user)
    assert out["email"] == "asha@example.com" and out["full_name"] == "Asha Rao"
    assert "password_hash" not in out
    token = AuthToken(user_id=uuid.uuid4(), purpose="email_verify", token_hash="h" * 64,
                      expires_at=dt.datetime(2026, 9, 30, tzinfo=dt.UTC))
    assert "token_hash" not in serialize(token)


def test_serialize_drops_internal_fields_and_stringifies_types():
    job = Job(
        id=uuid.uuid4(), user_id=uuid.uuid4(), raw_text="Backend role", title="Backend Engineer",
        extraction_meta={"model": "x"}, structured={"a": 1}, salary_min=100,
        posted_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
    )
    out = serialize(job)
    assert out["title"] == "Backend Engineer" and out["structured"] == {"a": 1}
    assert "extraction_meta" not in out and "user_id" not in out
    assert isinstance(out["id"], str) and out["posted_at"].startswith("2026-09-01")
    json.dumps(out)  # everything is JSON-safe


def test_zip_holds_the_data_a_readme_and_the_files():
    blob = build_zip(
        {"account": {"email": "asha@example.com", "score": Decimal("81.5")}},
        {"resumes/Asha Rao resume.pdf": b"%PDF-1.4 demo"},
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = set(z.namelist())
        assert names == {"mana-career-data.json", "README.txt", "resumes/Asha Rao resume.pdf"}
        data = json.loads(z.read("mana-career-data.json"))
        assert data["account"]["email"] == "asha@example.com"
        assert data["account"]["score"] == "81.5"
        assert z.read("resumes/Asha Rao resume.pdf") == b"%PDF-1.4 demo"
        assert b"mana-career-data.json" in z.read("README.txt")
