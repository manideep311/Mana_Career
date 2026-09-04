import uuid

from pydantic import TypeAdapter

from app.domain.agents.blocks import (
    InsufficientInfoBlock,
    JobCardBlock,
    ResponseBlock,
    TextBlock,
    dump_blocks,
)


def test_text_and_job_card_dump_to_tagged_dicts():
    jid = uuid.uuid4()
    out = dump_blocks([TextBlock(markdown="hi"), JobCardBlock(job_id=jid)])
    assert out[0] == {"kind": "text", "markdown": "hi"}
    assert out[1]["kind"] == "job_card" and out[1]["job_id"] == str(jid)
    assert out[1]["match_id"] is None


def test_discriminator_round_trips():
    ta = TypeAdapter(list[ResponseBlock])
    raw = [
        {"kind": "text", "markdown": "x"},
        {"kind": "job_card", "job_id": str(uuid.uuid4()), "match_id": str(uuid.uuid4())},
        {"kind": "insufficient_info", "topic": "job_match", "missing": ["a profile"]},
    ]
    parsed = ta.validate_python(raw)
    assert isinstance(parsed[0], TextBlock)
    assert isinstance(parsed[1], JobCardBlock)
    assert isinstance(parsed[2], InsufficientInfoBlock)


def test_unknown_kind_is_rejected():
    from pydantic import ValidationError

    ta = TypeAdapter(list[ResponseBlock])
    import pytest

    with pytest.raises(ValidationError):
        ta.validate_python([{"kind": "nope"}])
