from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter


class TextBlock(BaseModel):
    kind: Literal["text"] = "text"
    markdown: str


class JobCardBlock(BaseModel):
    kind: Literal["job_card"] = "job_card"
    job_id: uuid.UUID
    match_id: uuid.UUID | None = None


class InsufficientInfoBlock(BaseModel):
    kind: Literal["insufficient_info"] = "insufficient_info"
    topic: str
    missing: list[str] = Field(default_factory=list)


class MatchScoreBlock(BaseModel):
    kind: Literal["match_score"] = "match_score"
    match_id: uuid.UUID


class SkillGapBlock(BaseModel):
    kind: Literal["skill_gap"] = "skill_gap"
    match_id: uuid.UUID


class CareerRecommendationBlock(BaseModel):
    kind: Literal["career_recommendation"] = "career_recommendation"
    roadmap_id: uuid.UUID


class LearningRecommendationBlock(BaseModel):
    kind: Literal["learning_recommendation"] = "learning_recommendation"
    roadmap_id: uuid.UUID


class ResumeSuggestionBlock(BaseModel):
    kind: Literal["resume_suggestion"] = "resume_suggestion"
    suggestion_id: uuid.UUID


class ApplicationDraftBlock(BaseModel):
    kind: Literal["application_draft"] = "application_draft"
    application_id: uuid.UUID | None = None
    resume_version_id: uuid.UUID | None = None
    cover_letter_id: uuid.UUID | None = None
    email_draft_id: uuid.UUID | None = None


class ApprovalActionBlock(BaseModel):
    kind: Literal["approval_action"] = "approval_action"
    approval_id: uuid.UUID


ResponseBlock = Annotated[
    TextBlock
    | JobCardBlock
    | InsufficientInfoBlock
    | MatchScoreBlock
    | SkillGapBlock
    | CareerRecommendationBlock
    | LearningRecommendationBlock
    | ResumeSuggestionBlock
    | ApplicationDraftBlock
    | ApprovalActionBlock,
    Field(discriminator="kind"),
]

_BlockAdapter = TypeAdapter(list[ResponseBlock])


def dump_blocks(blocks: list[BaseModel]) -> list[dict[str, Any]]:
    return [b.model_dump(mode="json") for b in blocks]
