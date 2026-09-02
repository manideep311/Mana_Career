from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.errors import NotFoundError, ValidationAppError
from app.core.logging import current_request_id
from app.domain.profile.strength import ProfileCounts, compute_strength
from app.models.profile import (
    CareerProfile,
    ProfileCertification,
    ProfileEducation,
    ProfileExperience,
    ProfileProject,
)
from app.models.skill import ProfileSkill, Skill

SUBENTITY_MODELS: dict[str, type] = {
    "experiences": ProfileExperience,
    "education": ProfileEducation,
    "projects": ProfileProject,
    "certifications": ProfileCertification,
}
_SINGULAR = {
    "experiences": "experience",
    "education": "education",
    "projects": "project",
    "certifications": "certification",
}
_SCALAR_COLS = frozenset({
    "location", "github_url", "linkedin_url", "portfolio_url",
    "preferred_roles", "preferred_locations", "work_modes",
    "expected_salary_min", "expected_salary_max", "salary_currency",
    "salary_period", "years_experience", "seniority", "career_goals",
})


def _model(section: str) -> type:
    try:
        return SUBENTITY_MODELS[section]
    except KeyError:
        raise NotFoundError(detail=f"Unknown profile section '{section}'.") from None


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, user_id: uuid.UUID) -> CareerProfile:
        profile = (
            await self.session.execute(
                select(CareerProfile).where(CareerProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        if profile is None:
            profile = CareerProfile(user_id=user_id)
            self.session.add(profile)
            await self.session.flush()
            await self._recompute(profile)
        return profile

    async def _count(self, profile_id: uuid.UUID, model: type) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count()).select_from(model).where(
                        model.profile_id == profile_id  # type: ignore[attr-defined]
                    )
                )
            ).scalar_one()
        )

    async def _recompute(self, profile: CareerProfile) -> None:
        counts = ProfileCounts(
            experiences=await self._count(profile.id, ProfileExperience),
            education=await self._count(profile.id, ProfileEducation),
            projects=await self._count(profile.id, ProfileProject),
            certifications=await self._count(profile.id, ProfileCertification),
        )
        skill_count = await self._count(profile.id, ProfileSkill)
        result = compute_strength(profile, counts, skill_count=skill_count)
        profile.profile_strength = result.score
        profile.completeness = result.completeness
        await self.session.flush()

    async def _audit(
        self, action: str, user_id: uuid.UUID, meta: dict[str, Any] | None = None
    ) -> None:
        await audit(
            self.session,
            actor_type="user",
            action=action,
            actor_user_id=user_id,
            resource_type="career_profile",
            request_id=current_request_id(),
            meta=meta,
        )

    async def load_full(
        self, user_id: uuid.UUID
    ) -> tuple[CareerProfile, dict[str, list[Any]]]:
        profile = await self.get_or_create(user_id)
        sections = {
            name: await self.list_section(user_id, name) for name in SUBENTITY_MODELS
        }
        return profile, sections

    async def list_skills(
        self, user_id: uuid.UUID
    ) -> list[tuple[ProfileSkill, Skill]]:
        stmt = (
            select(ProfileSkill, Skill)
            .join(Skill, ProfileSkill.skill_id == Skill.id)
            .where(ProfileSkill.user_id == user_id)
            .order_by(Skill.category, Skill.label)
        )
        return list((await self.session.execute(stmt)).tuples().all())

    async def update_scalars(
        self, user_id: uuid.UUID, patch: dict[str, Any]
    ) -> CareerProfile:
        profile = await self.get_or_create(user_id)
        for key, value in patch.items():
            if key in _SCALAR_COLS:
                setattr(profile, key, value)
        await self.session.flush()
        await self._recompute(profile)
        await self._audit(
            "profile.update",
            user_id,
            {"fields": sorted(k for k in patch if k in _SCALAR_COLS)},
        )
        return profile

    async def list_section(self, user_id: uuid.UUID, section: str) -> list[Any]:
        model = _model(section)
        rows: list[Any] = list(
            (
                await self.session.execute(
                    select(model)
                    .where(model.user_id == user_id)  # type: ignore[attr-defined]
                    .order_by(model.order_index, model.id)  # type: ignore[attr-defined]
                )
            )
            .scalars()
            .all()
        )
        return rows

    async def _owned_item(
        self, user_id: uuid.UUID, section: str, item_id: uuid.UUID
    ) -> Any:
        model = _model(section)
        item = (
            await self.session.execute(
                select(model).where(
                    model.id == item_id,  # type: ignore[attr-defined]
                    model.user_id == user_id,  # type: ignore[attr-defined]
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise NotFoundError(detail=f"{_SINGULAR[section]} not found")
        return item

    async def add_item(
        self, user_id: uuid.UUID, section: str, data: dict[str, Any]
    ) -> Any:
        model = _model(section)
        profile = await self.get_or_create(user_id)
        order_index = await self._count(profile.id, model)
        item = model(
            user_id=user_id, profile_id=profile.id, order_index=order_index,
            source="user", **data,
        )
        self.session.add(item)
        await self.session.flush()
        await self._recompute(profile)
        await self._audit(
            f"profile.{_SINGULAR[section]}.create", user_id, {"id": str(item.id)}
        )
        return item

    async def update_item(
        self, user_id: uuid.UUID, section: str, item_id: uuid.UUID,
        patch: dict[str, Any],
    ) -> Any:
        item = await self._owned_item(user_id, section, item_id)
        for key, value in patch.items():
            setattr(item, key, value)
        await self.session.flush()
        await self._recompute(await self.get_or_create(user_id))
        await self._audit(
            f"profile.{_SINGULAR[section]}.update", user_id, {"id": str(item_id)}
        )
        return item

    async def delete_item(
        self, user_id: uuid.UUID, section: str, item_id: uuid.UUID
    ) -> None:
        item = await self._owned_item(user_id, section, item_id)
        await self.session.delete(item)
        await self.session.flush()
        await self._recompute(await self.get_or_create(user_id))
        await self._audit(
            f"profile.{_SINGULAR[section]}.delete", user_id, {"id": str(item_id)}
        )

    async def reorder(
        self, user_id: uuid.UUID, section: str, ordered_ids: list[uuid.UUID]
    ) -> list[Any]:
        current = await self.list_section(user_id, section)
        if {r.id for r in current} != set(ordered_ids) or len(ordered_ids) != len(current):
            raise ValidationAppError(
                detail="The id list must be a permutation of this section's items."
            )
        by_id = {r.id: r for r in current}
        for position, item_id in enumerate(ordered_ids):
            by_id[item_id].order_index = position
        await self.session.flush()
        await self._recompute(await self.get_or_create(user_id))
        return [by_id[i] for i in ordered_ids]
