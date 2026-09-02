from __future__ import annotations

import re

from app.core.errors import ValidationAppError

MAX_RAW_CHARS = 40_000
_MIN_MEANINGFUL = 20
_BLANK_RUN = re.compile(r"\n[ \t]*\n[ \t]*\n+")
_TRAIL_WS = re.compile(r"[ \t]+\n")
_LEAD_WS = re.compile(r"\n[ \t]+")


class JobIngestor:
    def clean(self, raw_text: str) -> str:
        s = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        s = _TRAIL_WS.sub("\n", s)
        s = _BLANK_RUN.sub("\n\n", s)
        s = _LEAD_WS.sub("\n", s)
        s = s.strip()[:MAX_RAW_CHARS].strip()
        if len(s) < _MIN_MEANINGFUL:
            raise ValidationAppError(code="job.empty")
        return s
