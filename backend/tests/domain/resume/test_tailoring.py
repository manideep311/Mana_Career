from app.domain.generation.service import GenerationService
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.resume.extractor import (
    ExtractedExperience,
    ResumeExtraction,
)
from app.domain.resume.tailoring import (
    ClaimValidator,
    _collect_sources,
    _resume_claim_lines,
    tailor_resume,
)


def _base() -> ResumeExtraction:
    return ResumeExtraction(
        full_name="A. Dev",
        summary="Backend engineer focused on Python services and Postgres.",
        skills=["python", "postgresql", "fastapi"],
        experiences=[
            ExtractedExperience(
                company="Acme", title="Senior Engineer",
                description="Owned the billing service.",
                highlights=[
                    "Cut p99 latency on the billing API by 40 percent",
                    "Migrated the datastore from MySQL to Postgres",
                ],
                tech=["python", "postgresql"],
            )
        ],
    )


def test_validator_passes_when_highlights_are_grounded():
    b = _base()
    v = ClaimValidator(_collect_sources(b, ""))
    report = v.check(_resume_claim_lines(b))  # the base is trivially grounded in itself
    assert report.passed is True
    assert report.unsupported == []


def test_validator_flags_an_invented_highlight():
    b = _base()
    v = ClaimValidator(_collect_sources(b, ""))
    tailored = b.model_copy(deep=True)
    tailored.experiences[0].highlights.append(
        "Led a team of 50 engineers across four continents"
    )
    report = v.check(_resume_claim_lines(tailored))
    assert report.passed is False
    assert any("Led a team of 50" in u for u in report.unsupported)


def test_validator_ignores_blank_and_structural_lines():
    b = _base()
    v = ClaimValidator(_collect_sources(b, ""))
    tailored = b.model_copy(deep=True)
    tailored.experiences[0].highlights.append("   ")
    report = v.check(_resume_claim_lines(tailored))
    assert report.passed is True


async def test_tailor_resume_loop_shape_with_fake_llm():
    b = _base()
    gen = GenerationService(FakeLLMProvider())
    tailored, meta = await tailor_resume(
        gen=gen, base=b, profile_summary="", job_brief="Senior Python role at Globex"
    )
    # FakeLLMProvider stubs the schema to empty → an empty extraction, 0 claims, passes.
    assert isinstance(tailored, ResumeExtraction)
    assert meta.claim_validation["checked"] == 0
    assert meta.claim_validation["passed"] is True
    assert meta.prompt_version == "tailor-1"
