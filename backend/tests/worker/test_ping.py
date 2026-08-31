from app.worker.tasks.ping import ping


async def test_ping_echoes_payload():
    out = await ping({"job_id": "job-1"}, "hello")
    assert out == {"echo": "hello", "job_id": "job-1"}


async def test_ping_default_payload():
    out = await ping({})
    assert out["echo"] == "pong"


def test_worker_settings_registers_ping():
    from app.worker.main import WorkerSettings

    assert ping in WorkerSettings.functions
    assert WorkerSettings.job_timeout == 300
