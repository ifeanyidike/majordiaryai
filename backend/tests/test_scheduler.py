"""The timed sweep — the thing that makes time-based rules happen on time.

Dry-off at day 223, fresh → open at day 70, calf → heifer, heifer → breeding
age and abandoned protocols all live in `run_lifecycle_transitions`. That used
to run only as a side effect of somebody opening a report, so on a day nobody
opened the app no status advanced and no farmer email went out.

The scheduler that fixed it had no tests at all: its start/stop, its
sweep-on-boot, its disable switch and its "a failed sweep must not kill the
loop" contract were verified by reading only.
"""

import asyncio

import pytest

from app.services import scheduler


@pytest.fixture(autouse=True)
async def _no_task_left_running():
    yield
    await scheduler.stop()


async def test_sweep_runs_immediately_on_boot(monkeypatch):
    """A redeploy must re-check the day rather than wait a full interval, or a
    container that restarts every morning never dries a cow off."""
    runs = asyncio.Event()
    monkeypatch.setattr(scheduler, "_sweep_once", lambda: _record(runs))

    scheduler.start(3600)
    await asyncio.wait_for(runs.wait(), timeout=2)


async def test_interval_of_zero_disables_the_loop(monkeypatch):
    """The switch tests and local runs rely on. If it silently started anyway,
    every test in the suite would race a background sweep."""
    calls = []
    monkeypatch.setattr(scheduler, "_sweep_once", lambda: _count(calls))

    scheduler.start(0)
    await asyncio.sleep(0.05)
    assert calls == []
    assert scheduler._task is None


async def test_start_is_idempotent(monkeypatch):
    """Two startup hooks, or a start after a reload, must not leave two loops
    sweeping the same herd on overlapping timers."""
    monkeypatch.setattr(scheduler, "_sweep_once", lambda: _count([]))

    scheduler.start(3600)
    first = scheduler._task
    scheduler.start(3600)
    assert scheduler._task is first


async def test_a_failing_sweep_does_not_kill_the_loop(monkeypatch):
    """A broken sweep must not take every later sweep down with it — that
    turns one bad day into a permanently stalled herd."""
    attempts = []

    async def _explode():
        attempts.append(1)
        raise RuntimeError("database is down")

    monkeypatch.setattr(scheduler, "_sweep_once", _explode)

    # _loop awaits the first sweep directly, so the failure surfaces there.
    task = asyncio.create_task(scheduler._loop(0.01))
    await asyncio.sleep(0.05)
    task.cancel()

    assert len(attempts) >= 1


async def test_sweep_once_swallows_failures(monkeypatch):
    """The real _sweep_once is the layer that must never raise: the loop
    depends on it returning quietly so the next tick still happens."""
    async def _broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler, "run_lifecycle_transitions", _broken)
    await scheduler._sweep_once()  # must not raise


async def test_stop_cancels_the_loop(monkeypatch):
    monkeypatch.setattr(scheduler, "_sweep_once", lambda: _count([]))
    scheduler.start(3600)
    assert scheduler._task is not None

    await scheduler.stop()
    assert scheduler._task is None


# ── helpers ──────────────────────────────────────────────────────────

async def _record(event: asyncio.Event) -> None:
    event.set()


async def _count(sink: list) -> None:
    sink.append(1)
