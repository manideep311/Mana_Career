from __future__ import annotations

import uuid

from pydantic import BaseModel


class LearningResourceOut(BaseModel):
    id: uuid.UUID
    title: str
    provider: str
    url: str
    type: str
    skills: list[str]
    level: str
    est_hours: int | None
    cost: str
    summary: str
