from eval.run import _amain


async def test_cli_exits_zero_when_thresholds_clear(capsys):
    code = await _amain(["retrieval", "--provider", "fake"])
    assert code == 0
    out = capsys.readouterr().out
    assert "recall_at_10" in out and "pass" in out.lower()


async def test_cli_json_flag_emits_json(capsys):
    code = await _amain(["retrieval", "--provider", "fake", "--json"])
    assert code == 0
    import json

    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "aggregate" in payload and payload["passed"] is True
