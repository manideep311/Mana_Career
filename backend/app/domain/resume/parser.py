from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.core.config import Settings
from app.core.errors import ValidationAppError

MIN_DIGITAL_TEXT_CHARS = 120

# One source of truth for the "this PDF has no extractable text" message, shared
# by the OCR stub and the worker's scanned-PDF branch.
SCANNED_PDF_MESSAGE = (
    "This looks like a scanned PDF — text extraction isn't available yet. "
    "Try uploading a text-based PDF."
)


@dataclass(frozen=True)
class ParsedResume:
    """Parsed resume data from PDF extraction."""

    text: str
    page_count: int


class ResumeParser(Protocol):
    """Protocol for resume PDF parsing."""

    async def parse(self, data: bytes) -> ParsedResume:
        """Parse resume PDF data.

        Args:
            data: Binary PDF data

        Returns:
            ParsedResume with extracted text and page count

        Raises:
            ValidationAppError: If parsing fails
        """
        ...


class PypdfResumeParser:
    """Resume parser using pypdf for digital text extraction."""

    async def parse(self, data: bytes) -> ParsedResume:
        """Parse resume PDF using pypdf.

        Args:
            data: Binary PDF data

        Returns:
            ParsedResume with extracted text and page count

        Raises:
            ValidationAppError: If PDF is unreadable
        """
        return await asyncio.to_thread(self._sync_parse, data)

    @staticmethod
    def _sync_parse(data: bytes) -> ParsedResume:
        """Synchronous PDF parsing (to be run in thread pool)."""
        try:
            reader = PdfReader(BytesIO(data))
            page_count = len(reader.pages)
            text = "\n\n".join(
                p.extract_text() or "" for p in reader.pages
            ).strip()
            return ParsedResume(text=text, page_count=page_count)
        except PyPdfError as exc:
            raise ValidationAppError(code="resume.unreadable_pdf") from exc


class OcrResumeParser:
    """OCR resume parser stub (not yet implemented)."""

    async def parse(self, data: bytes) -> ParsedResume:
        """Parse resume PDF using OCR (stub).

        Args:
            data: Binary PDF data

        Returns:
            Never (always raises)

        Raises:
            ValidationAppError: Always raises with ocr_unavailable code
        """
        raise ValidationAppError(
            detail=SCANNED_PDF_MESSAGE,
            code="resume.ocr_unavailable",
        )


def get_resume_parser(settings: Settings) -> ResumeParser:
    """Get resume parser instance.

    Args:
        settings: Application settings

    Returns:
        ResumeParser instance (currently always PypdfResumeParser)
    """
    return PypdfResumeParser()
