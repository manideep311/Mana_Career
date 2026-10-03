"""What a person approves: a canonical snapshot of the application and its hash.

The hash is checked again right before sending, so anything that changes after
review (the letter, the email, the recipient) stops the send.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.models.application import ApplicationEmail, CoverLetter


def build_snapshot(
    job_title: str, company: str, resume_version_id: str | None,
    letter: CoverLetter, email: ApplicationEmail,
) -> dict[str, Any]:
    return {
        "job": {"title": job_title, "company": company},
        "resume_version_id": resume_version_id,
        "cover_letter": {"id": str(letter.id), "content": letter.content},
        "email": {
            "id": str(email.id), "to_email": email.to_email, "to_name": email.to_name,
            "subject": email.subject, "body": email.body,
        },
    }


def hash_snapshot(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
