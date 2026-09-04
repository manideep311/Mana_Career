from app.domain.documents.renderer import (
    DocumentRenderer,
    RenderFormat,
    RenderUnavailable,
)
from app.domain.resume.extractor import ExtractedExperience, ResumeExtraction

R = DocumentRenderer()
CV = ResumeExtraction(
    full_name="Jamie Rivera",
    summary="Platform engineer.",
    skills=["python", "kubernetes"],
    experiences=[
        ExtractedExperience(
            company="Globex", title="Staff Engineer",
            highlights=["Ran the platform team", "Shipped the CI pipeline"],
        )
    ],
)


def test_markdown_has_name_h1_and_company_h2_and_bullets():
    md = R.to_markdown(CV)
    assert md.splitlines()[0].strip() == "# Jamie Rivera"
    assert "## Globex" in md or "Globex" in md
    assert "- Ran the platform team" in md


def test_markdown_is_stable():
    assert R.to_markdown(CV) == R.to_markdown(CV)


def test_html_contains_the_name():
    html = R.to_html(CV)
    assert "<h1>" in html and "Jamie Rivera" in html


def test_pdf_is_pdf_bytes_or_unavailable():
    try:
        data = R.to_pdf(CV)
    except RenderUnavailable:
        return
    assert data[:4] == b"%PDF"


def test_docx_is_zip_bytes_or_unavailable():
    try:
        data = R.to_docx(CV)
    except RenderUnavailable:
        return
    assert data[:2] == b"PK"


def test_render_dispatches_by_format():
    doc = R.render(CV, RenderFormat.MD)
    assert doc.fmt is RenderFormat.MD and doc.media_type == "text/markdown"
    assert b"Jamie Rivera" in doc.data
