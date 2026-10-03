"""Export + deletion against the real schema -- DB integration, CI-deferred."""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from sqlalchemy import func, or_, select

from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError
from app.domain.account.deletion import AccountDeleter
from app.domain.account.export import AccountExporter
from app.infra.storage.local import LocalFileStore
from app.models.ai import AiAction, AiSession, Message
from app.models.application import Application, ApplicationEmail, ApprovalRequest, CoverLetter
from app.models.audit import AuditLog
from app.models.job import Job
from app.models.learning import LearningRecommendation
from app.models.profile import CareerProfile, ProfileExperience
from app.models.resume import Resume
from app.models.user import User

from .conftest import PASSWORD

USER_TABLES = (
    CareerProfile, ProfileExperience, Resume, Job, AiSession, Message, AiAction,
    CoverLetter, ApplicationEmail, Application, ApprovalRequest, LearningRecommendation,
)


class _Saver:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


async def _counts(db_session, user_id) -> dict[str, int]:
    out = {}
    for model in USER_TABLES:
        out[model.__tablename__] = (
            await db_session.execute(
                select(func.count()).select_from(model).where(model.user_id == user_id)
            )
        ).scalar_one()
    return out


# --------------------------------------------------------------------- export


async def test_export_contains_their_data_and_their_files(db_session, seed_person, tmp_path):
    store = LocalFileStore(str(tmp_path))
    me = await seed_person("export-me@x.com", store=store, pdf=b"%PDF-1.4 mine")
    await seed_person("export-other@x.com", store=store, pdf=b"%PDF-1.4 theirs")

    filename, blob = await AccountExporter(db_session, store).export(me.user)
    assert filename.startswith("mana-career-export-") and filename.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        data = json.loads(z.read("mana-career-data.json"))
        assert z.read("resumes/Asha Rao CV.pdf") == b"%PDF-1.4 mine"
        raw = z.read("mana-career-data.json").decode()

    assert data["account"]["email"] == "export-me@x.com"
    assert data["experiences"][0]["company"] == "Acme"
    assert "FastAPI" in data["resumes"][0]["extracted_text"]
    assert data["resumes"][0]["file_in_export"] == "resumes/Asha Rao CV.pdf"
    assert [j["title"] for j in data["saved_jobs"]] == ["Platform Engineer"]
    assert data["cover_letters"][0]["content"].startswith("Dear Initech")
    assert data["mana_ai_messages"][0]["content"] == "Help me apply to Initech"
    # Only their own rows, and no secrets.
    assert "export-other@x.com" not in raw
    assert "password_hash" not in raw and "payload_hash" not in raw


# ------------------------------------------------------------------- deletion


async def test_deletion_leaves_nothing_of_theirs_and_spares_everyone_else(
    db_session, seed_person, tmp_path
):
    store = LocalFileStore(str(tmp_path))
    me = await seed_person("delete-me@x.com", store=store)
    other = await seed_person("delete-other@x.com", store=store)
    uid, other_before = me.user.id, await _counts(db_session, other.user.id)
    assert all(n >= 1 for n in (await _counts(db_session, uid)).values())

    saver = _Saver()

    async def factory(_settings):
        return saver

    deleter = AccountDeleter(db_session, get_settings(), store, checkpointer=factory)
    plan = await deleter.delete(me.user, PASSWORD)
    await db_session.flush()
    await deleter.cleanup(plan)

    assert await db_session.get(User, uid) is None
    assert all(n == 0 for n in (await _counts(db_session, uid)).values())
    assert await _counts(db_session, other.user.id) == other_before

    # Files and agent run state are gone for them only.
    with pytest.raises(NotFoundError):
        await store.get(me.file_ref)
    assert await store.get(other.file_ref)
    assert saver.deleted == [me.run_id]

    # The security trail keeps what happened, minus anything personal.
    audit_rows = (
        await db_session.execute(
            select(AuditLog).where(
                or_(AuditLog.actor_user_id == uid, AuditLog.on_behalf_of_user_id == uid)
            )
        )
    ).scalars().all()
    actions = {a.action for a in audit_rows}
    assert {"auth.login", "account.deleted"} <= actions
    assert all(a.ip is None and a.user_agent is None for a in audit_rows)
    assert all(a.before is None and a.after is None for a in audit_rows)
    others = (
        await db_session.execute(select(AuditLog).where(AuditLog.actor_user_id == other.user.id))
    ).scalars().all()
    assert all(a.ip == "203.0.113.7" for a in others)


async def test_a_wrong_password_deletes_nothing(db_session, seed_person, tmp_path):
    store = LocalFileStore(str(tmp_path))
    me = await seed_person("delete-typo@x.com", store=store)
    before = await _counts(db_session, me.user.id)
    deleter = AccountDeleter(db_session, get_settings(), store)
    with pytest.raises(ForbiddenError):
        await deleter.delete(me.user, "not-my-password")
    assert await db_session.get(User, me.user.id) is not None
    assert await _counts(db_session, me.user.id) == before
    assert await store.get(me.file_ref)
