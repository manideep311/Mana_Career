from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, cast

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.embeddings.provider import EmbeddingsProvider
from app.models.skill import Skill

_WS_RE = re.compile(r"\s+")
_EDGE_RE = re.compile(r"^[^a-z0-9+#.]+|[^a-z0-9+#.]+$")


@dataclass(frozen=True)
class SkillMatch:
    skill_id: uuid.UUID
    slug: str
    label: str
    method: Literal["exact", "embedding"]
    score: float


class SkillNormalizer:
    """Resolve a free-text skill string to a taxonomy row.

    An exact match on the normalised slug or any normalised alias wins with
    ``score == 1.0``. Otherwise, when the taxonomy carries embeddings, the
    nearest row by cosine similarity is returned when it clears ``threshold``.
    Call :meth:`load` once before :meth:`normalize` / :meth:`normalize_many`.
    """

    def __init__(
        self,
        session: AsyncSession,
        embeddings: EmbeddingsProvider,
        *,
        threshold: float = 0.82,
    ) -> None:
        self.session = session
        self.embeddings = embeddings
        self.threshold = threshold
        self._exact: dict[str, tuple[uuid.UUID, str, str]] = {}
        self._has_embeddings = False

    @staticmethod
    def _norm(s: str) -> str:
        """Lower-case, collapse internal whitespace, trim edge punctuation.

        Characters in ``[a-z0-9+#.]`` survive at the edges so ``c++``, ``c#``
        and ``node.js`` are preserved.
        """
        s = _WS_RE.sub(" ", s.strip().lower())
        return _EDGE_RE.sub("", s)

    async def load(self) -> None:
        self._exact = {}
        rows = (
            await self.session.execute(
                select(Skill.id, Skill.slug, Skill.label, Skill.aliases)
                .order_by(Skill.slug)
            )
        ).all()
        # Two passes so a slug (or label) always beats another entry's alias,
        # and among aliases the lowest slug wins deterministically.
        for row in rows:
            entry = (row.id, row.slug, row.label)
            for key in (row.slug, row.label):
                nkey = self._norm(key)
                if nkey and nkey not in self._exact:
                    self._exact[nkey] = entry
        for row in rows:
            entry = (row.id, row.slug, row.label)
            for key in row.aliases:
                nkey = self._norm(key)
                if nkey and nkey not in self._exact:
                    self._exact[nkey] = entry
        self._has_embeddings = (
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(Skill)
                    .where(Skill.embedding.is_not(None))
                )
            ).scalar_one()
            > 0
        )

    async def normalize(self, raw: str) -> SkillMatch | None:
        hit = self._exact.get(self._norm(raw))
        if hit is not None:
            skill_id, slug, label = hit
            return SkillMatch(
                skill_id=skill_id,
                slug=slug,
                label=label,
                method="exact",
                score=1.0,
            )
        if not self._has_embeddings:
            return None

        query_vec = await self.embeddings.embed_query(raw)
        distance = cast(
            ColumnElement[float], Skill.embedding.cosine_distance(query_vec)
        )
        row = (
            await self.session.execute(
                select(Skill.id, Skill.slug, Skill.label, distance.label("distance"))
                .where(Skill.embedding.is_not(None))
                .order_by(distance)
                .limit(1)
            )
        ).first()
        if row is None:
            return None
        score = 1.0 - float(row.distance)
        if score < self.threshold:
            return None
        return SkillMatch(
            skill_id=row.id,
            slug=row.slug,
            label=row.label,
            method="embedding",
            score=score,
        )

    async def normalize_many(self, raws: Iterable[str]) -> dict[str, SkillMatch]:
        first_seen: dict[str, str] = {}
        for raw in raws:
            first_seen.setdefault(self._norm(raw), raw)
        out: dict[str, SkillMatch] = {}
        for original in first_seen.values():
            match = await self.normalize(original)
            if match is not None:
                out[original] = match
        return out
