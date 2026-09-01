import io

import pytest
from pypdf import PdfWriter

from app.core.errors import ValidationAppError
from app.domain.resume.parser import OcrResumeParser, PypdfResumeParser


def _pdf_bytes(pages: int = 1) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


async def test_parses_page_count():
    parsed = await PypdfResumeParser().parse(_pdf_bytes(pages=3))
    assert parsed.page_count == 3
    assert isinstance(parsed.text, str)


async def test_rejects_non_pdf_bytes():
    with pytest.raises(ValidationAppError):
        await PypdfResumeParser().parse(b"this is not a pdf")


async def test_ocr_stub_raises():
    with pytest.raises(ValidationAppError):
        await OcrResumeParser().parse(_pdf_bytes())
