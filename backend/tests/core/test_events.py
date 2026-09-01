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


async def test_status_stream_opens_relays_and_closes_on_terminal():
    ps = _FakePubSub([
        {"data": json.dumps({"event": "status", "status": "parsing"})},
        {"data": json.dumps({"event": "status", "status": "extracted"})},
    ])
    out = [
        ev
        async for ev in status_stream(
            _FakeRedisForStream(ps), "ch", terminal={"extracted", "failed"}
        )
    ]
    assert out[0] == {"event": "open"}
    assert ps.subscribed_to == "ch"  # subscribe happened before the first yield
    assert out[-1]["status"] == "extracted"
    assert ps.unsubscribed and ps.closed
