"""The learning-resource catalog JSON is well-formed."""
from __future__ import annotations

import json
from pathlib import Path

_VALID_TYPE = {"course", "book", "doc", "video", "article", "project"}
_VALID_LEVEL = {"beginner", "intermediate", "advanced"}
_VALID_COST = {"free", "paid", "freemium"}


def test_catalog_entries_are_valid():
    path = Path("app/domain/roadmap/learning_resources.json")
    entries = json.loads(path.read_text("utf-8"))
    assert len(entries) >= 40
    urls = [e["url"] for e in entries]
    assert len(urls) == len(set(urls)), "duplicate url in catalog"
    for e in entries:
        assert e["type"] in _VALID_TYPE
        assert e["level"] in _VALID_LEVEL
        assert e["cost"] in _VALID_COST
        assert isinstance(e["skills"], list) and e["skills"]
        assert e["summary"] and e["title"] and e["provider"]
