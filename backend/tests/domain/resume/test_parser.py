import base64
import io

import pytest
from pypdf import PdfWriter

from app.core.config import Settings, get_settings
from app.core.errors import ValidationAppError
from app.domain.resume.parser import (
    OcrResumeParser,
    Pdfium2ResumeParser,
    PypdfResumeParser,
    get_resume_parser,
)

# Minimal 1-page PDF whose content stream draws two text lines. Hand-built so
# the test needs no PDF-writer that can lay down text; verified to read
# identically under both PDFium and pypdf.
_TEXT_PDF = base64.b64decode(
    "JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2Jq"
    "CjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4KZW5kb2Jq"
    "CjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCAzMjAg"
    "MjAwXSAvUmVzb3VyY2VzIDw8IC9Gb250IDw8IC9GMSA0IDAgUiA+PiA+PiAvQ29udGVudHMgNSAw"
    "IFIgPj4KZW5kb2JqCjQgMCBvYmoKPDwgL1R5cGUgL0ZvbnQgL1N1YnR5cGUgL1R5cGUxIC9CYXNl"
    "Rm9udCAvSGVsdmV0aWNhID4+CmVuZG9iago1IDAgb2JqCjw8IC9MZW5ndGggODIgPj4Kc3RyZWFt"
    "CkJUIC9GMSAxOCBUZiAyMCAxNTAgVGQgKEphbmUgRGV2ZWxvcGVyKSBUaiAwIC0zMCBUZCAoU2Vu"
    "aW9yIFB5dGhvbiBFbmdpbmVlcikgVGogRVQKZW5kc3RyZWFtCmVuZG9iagp4cmVmCjAgNgowMDAw"
    "MDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMDkgMDAwMDAgbiAKMDAwMDAwMDA1OCAwMDAwMCBuIAow"
    "MDAwMDAwMTE1IDAwMDAwIG4gCjAwMDAwMDAyNDEgMDAwMDAgbiAKMDAwMDAwMDMxMSAwMDAwMCBu"
    "IAp0cmFpbGVyCjw8IC9TaXplIDYgL1Jvb3QgMSAwIFIgPj4Kc3RhcnR4cmVmCjQ0MwolJUVPRg=="
)


def _blank_pdf_bytes(pages: int = 1) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


async def test_parses_page_count():
    parsed = await PypdfResumeParser().parse(_blank_pdf_bytes(pages=3))
    assert parsed.page_count == 3
    assert isinstance(parsed.text, str)


async def test_rejects_non_pdf_bytes():
    with pytest.raises(ValidationAppError):
        await PypdfResumeParser().parse(b"this is not a pdf")


async def test_ocr_stub_raises():
    with pytest.raises(ValidationAppError):
        await OcrResumeParser().parse(_blank_pdf_bytes())


# --- Pdfium2ResumeParser -------------------------------------------------------


async def test_pdfium_reports_page_count():
    parsed = await Pdfium2ResumeParser().parse(_blank_pdf_bytes(pages=3))
    assert parsed.page_count == 3


async def test_pdfium_extracts_text():
    parsed = await Pdfium2ResumeParser().parse(_TEXT_PDF)
    assert parsed.page_count == 1
    assert "Jane Developer" in parsed.text
    assert "Senior Python Engineer" in parsed.text
    assert "\r" not in parsed.text  # CRLF normalised


async def test_pdfium_falls_back_to_pypdf_when_pdfium_cannot_open(monkeypatch):
    """A file PDFium refuses is retried with pypdf before we give up."""
    calls: list[str] = []

    real_pypdf_parse = PypdfResumeParser.parse

    async def _spy(self: PypdfResumeParser, data: bytes) -> object:
        calls.append("pypdf")
        return await real_pypdf_parse(self, data)

    monkeypatch.setattr(PypdfResumeParser, "parse", _spy)

    parser = Pdfium2ResumeParser()
    # Not a PDF: PDFium raises -> _PdfiumFailure -> fallback -> pypdf also
    # raises ValidationAppError, which is what surfaces.
    with pytest.raises(ValidationAppError):
        await parser.parse(b"definitely not a pdf")
    assert calls == ["pypdf"]


async def test_get_resume_parser_honours_setting():
    pdfium_settings = get_settings().model_copy(update={"resume_parser": "pdfium"})
    assert isinstance(get_resume_parser(pdfium_settings), Pdfium2ResumeParser)

    pypdf_settings = get_settings().model_copy(update={"resume_parser": "pypdf"})
    assert isinstance(get_resume_parser(pypdf_settings), PypdfResumeParser)


def test_default_resume_parser_is_pdfium():
    assert Settings.model_fields["resume_parser"].default == "pdfium"
