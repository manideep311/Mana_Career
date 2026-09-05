from app.domain.generation.email_draft import EmailDraft, draft_email
from app.domain.generation.service import GenerationService
from app.domain.llm.adapters.fake import FakeLLMProvider


async def test_draft_email_shape_with_fake_llm():
    gen = GenerationService(FakeLLMProvider())
    draft, meta = await draft_email(
        gen=gen,
        job_title="Senior Backend Engineer",
        company="Globex",
        applicant_name="A. Dev",
        cover_letter_content="Dear Hiring Team,\n\nI am excited to apply.\n\nSincerely,\nA. Dev",
    )
    assert isinstance(draft, EmailDraft)
    assert draft.subject == ""  # FakeLLMProvider stubs str fields to ""
    assert meta.prompt_version == "email-draft-1"
