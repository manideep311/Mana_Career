import json

from app.core.events import resume_channel, sse_event, status_stream


def test_resume_channel():
    assert resume_channel("abc") == "sse:resume:abc"


def test_sse_event_shape():
    ev = sse_event({"event": "status", "resource": "resume", "id": "r1",
                    "status": "parsed", "message": "Understood your résumé"})
    assert ev.event == "status"
    assert json.loads(ev.data)["status"] == "parsed"


class _FakePubSub:
    def __init__(self, messages):  # messages: list[dict | None]
        self._messages = list(messages)
        self.subscribed_to = None
        self.unsubscribed = False
        self.closed = False

    async def subscribe(self, channel):
        self.subscribed_to = channel

    async def get_message(self, *, ignore_subscribe_messages, timeout):  # noqa: ASYNC109
        return self._messages.pop(0) if self._messages else None

    async def unsubscribe(self, channel):
        self.unsubscribed = True

    async def aclose(self):
        self.closed = True


class _FakeRedisForStream:
    def __init__(self, pubsub):
        self._pubsub = pubsub

    def pubsub(self):
        return self._pubsub


async def test_status_stream_emits_done_after_terminal_status():
    ps = _FakePubSub([
        {"data": json.dumps({"event": "status", "status": "parsing"})},
        {"data": json.dumps({"event": "status", "status": "extracted"})},
    ])
    out = [
        ev async for ev in status_stream(
            _FakeRedisForStream(ps), "ch", terminal={"extracted", "failed"}
        )
    ]
    assert out[0] == {"event": "open"}
    # Subscribe happens before the first yield — this is what makes `open` and
    # race-free reconnect work.
    assert ps.subscribed_to == "ch"
    assert out[-2]["status"] == "extracted"
    assert out[-1] == {"event": "done", "status": "extracted", "totals": {}}
    assert ps.unsubscribed and ps.closed


async def test_status_stream_emits_error_on_malformed_payload():
    ps = _FakePubSub([{"data": "not-json"}])
    out = [
        ev async for ev in status_stream(
            _FakeRedisForStream(ps), "ch", terminal={"extracted", "failed"}
        )
    ]
    assert out[0] == {"event": "open"}
    assert out[-1]["event"] == "error"
    assert out[-1]["code"] == "stream.bad_payload"
    assert ps.unsubscribed and ps.closed


async def test_status_stream_skips_keepalive_timeouts_without_a_ping_frame():
    ps = _FakePubSub([
        None,  # a get_message() timeout
        {"data": json.dumps({"event": "status", "status": "extracted"})},
    ])
    out = [
        ev async for ev in status_stream(
            _FakeRedisForStream(ps), "ch", terminal={"extracted", "failed"}
        )
    ]
    assert {"event": "ping"} not in out
    assert out[-1] == {"event": "done", "status": "extracted", "totals": {}}
