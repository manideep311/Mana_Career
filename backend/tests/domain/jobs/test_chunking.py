from app.domain.jobs.chunking import chunk_job, estimate_tokens
from app.domain.jobs.extractor import JDSkill, JobExtraction


def test_chunk_job_emits_one_chunk_per_nonempty_section_with_running_index():
    ex = JobExtraction(
        description="We build low-latency inference services.",
        responsibilities=["Own the serving stack", "Mentor two engineers"],
        required_skills=[JDSkill(raw="Python", weight=0.9)],
        preferred_skills=[JDSkill(raw="Rust", weight=0.3)],
    )
    chunks = chunk_job(ex)
    sections = [c.section for c in chunks]
    assert sections == ["description", "responsibilities", "requirements"]
    assert [c.chunk_index for c in chunks] == [0, 1, 2]
    assert "Own the serving stack" in chunks[1].content
    assert "Required: Python" in chunks[2].content and "Preferred: Rust" in chunks[2].content
    assert all(c.token_count == estimate_tokens(c.content) for c in chunks)


def test_chunk_job_splits_a_long_section_with_overlap():
    long_desc = " ".join(f"w{i}" for i in range(900))
    chunks = chunk_job(JobExtraction(description=long_desc), max_tokens=300, overlap=40)
    desc_chunks = [c for c in chunks if c.section == "description"]
    assert len(desc_chunks) >= 3
    assert all(c.token_count <= 300 for c in desc_chunks)
    # consecutive windows overlap
    first_tail = desc_chunks[0].content.split()[-40:]
    assert any(w in desc_chunks[1].content.split()[:60] for w in first_tail)


def test_chunk_job_skips_empty_sections():
    chunks = chunk_job(JobExtraction(responsibilities=["Only this"]))
    assert [c.section for c in chunks] == ["responsibilities"]
    assert chunks[0].chunk_index == 0
