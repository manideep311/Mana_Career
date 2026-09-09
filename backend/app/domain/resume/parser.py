from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

import pypdfium2 as pdfium
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


class _PdfiumFailure(Exception):
    """Internal sentinel: PDFium could not open the document — try the fallback."""


class Pdfium2ResumeParser:
    """Fast PDF text extraction via PDFium, with a pypdf fallback.

    PDFium (the engine inside Chrome) extracts text roughly an order of
    magnitude faster than pypdf's pure-Python path on styled / multi-column
    résumés. When PDFium fails to open a file, or comes back nearly empty from
    a PDF that clearly has pages, we retry once with :class:`PypdfResumeParser`
    so a quirky file still parses.
    """

    def __init__(self) -> None:
        self._fallback = PypdfResumeParser()

    async def parse(self, data: bytes) -> ParsedResume:
        try:
            parsed = await asyncio.to_thread(self._sync_parse, data)
        except _PdfiumFailure:
            return await self._fallback.parse(data)
        if parsed.page_count > 0 and len(parsed.text) < MIN_DIGITAL_TEXT_CHARS:
            # PDFium came back nearly empty — a font/encoding quirk pypdf may
            # handle better. Take pypdf's result only if it actually got more.
            alt = await self._fallback.parse(data)
            if len(alt.text) > len(parsed.text):
                return alt
        return parsed

    @staticmethod
    def _sync_parse(data: bytes) -> ParsedResume:
        try:
            doc = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as exc:
            raise _PdfiumFailure from exc
        try:
            page_count = len(doc)
            chunks: list[str] = []
            for i in range(page_count):
                page = doc[i]
                textpage = page.get_textpage()
                try:
                    chunks.append(textpage.get_text_range() or "")
                finally:
                    textpage.close()
                    page.close()
            text = "\n\n".join(chunks).replace("\r\n", "\n").strip()
            return ParsedResume(text=text, page_count=page_count)
        finally:
            doc.close()


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
    """Return the configured résumé parser.

    ``RESUME_PARSER=pdfium`` (default) → :class:`Pdfium2ResumeParser` (fast,
    pypdf fallback baked in). ``RESUME_PARSER=pypdf`` → :class:`PypdfResumeParser`
    only — the pure-Python path, kept as an escape hatch.
    """
    if settings.resume_parser == "pypdf":
        return PypdfResumeParser()
    return Pdfium2ResumeParser()
