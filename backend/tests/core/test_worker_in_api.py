"""RUN_WORKER_IN_API: the worker starts with the API and stops with it."""
from __future__ import annotations

import asyncio

import app.main as main_module


class _FakeWorker:
    def __init__(self) -> None:
        self.running = asyncio.Event()
        self.closed = False

    async def async_run(self) -> None:
        self.running.set()
        await asyncio.Event().wait()  # polls until cancelled

    async def close(self) -> None:
        self.closed = True


async def test_the_worker_runs_for_the_life_of_the_api(monkeypatch):
    fake = _FakeWorker()
    monkeypatch.setattr(main_module, "_start_worker", lambda: fake)
    settings = main_module.get_settings().model_copy(update={"run_worker_in_api": True})
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)

    async with main_module._lifespan(main_module.app):
        await asyncio.wait_for(fake.running.wait(), timeout=2)
        assert not fake.closed
    assert fake.closed


async def test_off_by_default(monkeypatch):
    def boom():
        raise AssertionError("the worker must not start")

    monkeypatch.setattr(main_module, "_start_worker", boom)
    async with main_module._lifespan(main_module.app):
        pass
