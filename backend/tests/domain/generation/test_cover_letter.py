from app.domain.generation.cover_letter import (
    CoverLetterDraft,
    _collect_sources,
    write_cover_letter,
)
from app.domain.generation.service import GenerationService
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.resume.extractor import ExtractedExperience, ResumeExtraction
from app.domain.resume.tailoring import ClaimValidator


def _base() -> ResumeExtraction:
    return ResumeExtraction(
        full_name="A. Dev",
        summary="Backend engineer focused on Python services and Postgres.",
        skills=["python", "postgresql"],
        experiences=[
            ExtractedExperience(
                company="Acme", title="Senior Engineer",
                description="Owned the billing service.",
                highlights=["Cut p99 latency on the billing API by 40 percent"],
            )
        ],
    )


def test_collect_sources_includes_job_brief():
    b = _base()
    sources = _collect_sources(b, "", "We build resilient payments infrastructure.")
    assert any("resilient payments" in s for s in sources)


def test_validator_flags_an_invented_claim_in_a_letter():
    b = _base()
    sources = _collect_sources(b, "", "")
    v = ClaimValidator(sources)
    report = v.check(["I previously led a team of 200 engineers."])
    assert report.passed is False


async def test_write_cover_letter_loop_shape_with_fake_llm():
    b = _base()
    gen = GenerationService(FakeLLMProvider())
    draft, meta = await write_cover_letter(
        gen=gen, base=b, profile_summary="", job_brief="Senior Python role at Globex"
    )
    # FakeLLMProvider stubs the schema to empty -> an empty letter, 0 claims, passes.
    assert isinstance(draft, CoverLetterDraft)
    assert draft.content == ""
    assert meta.claim_validation["checked"] == 0
    assert meta.claim_validation["passed"] is True
    assert meta.prompt_version == "cover-letter-1"
