"""Runs the lifecycle sweep on a timer, not just when someone opens a report.

Every time-based rule in the system — dry-off at day 223, fresh → open at day
70, calf → heifer, heifer → breeding age, abandoned protocols — lives in
`run_lifecycle_transitions`. That used to run ONLY as a side effect of a report
request, so on a day nobody opened the app no status advanced and no farmer
email went out. The behaviour was coupled to app usage instead of to time.

This is an in-process loop rather than a separate Railway cron service: it
needs no extra service or cost, and the sweep is safe to run repeatedly because
each transition is guarded by the status it changes (a cow that is already Dry
is not swept again). Duplicate runs across multiple instances are therefore
harmless — worst case is a little wasted work, never a duplicate email.

The trade-off vs. a real cron: the timer resets when the container restarts.
That is covered by sweeping once on startup, so a restart re-checks rather than
skipping a day.
"""

import asyncio
import logging
from typing import Optional

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.status_engine import run_lifecycle_transitions

logger = logging.getLogger("app.scheduler")

_task: Optional[asyncio.Task] = None


async def _sweep_once() -> None:
    """One pass over every farm. Failures are logged, never fatal — a broken
    sweep must not take the API down with it."""
    try:
        async with SessionLocal() as session:
            changed = await run_lifecycle_transitions(session, farm_ids=None)
        if changed:
            logger.info("Lifecycle sweep applied %s transition(s)", changed)
        else:
            logger.debug("Lifecycle sweep: nothing to do")
    except Exception:
        logger.exception("Lifecycle sweep failed; will retry on the next tick")


async def _loop(interval_seconds: int) -> None:
    # Sweep immediately on boot so a restart re-checks the day rather than
    # waiting a full interval (and so a redeploy never skips a dry-off).
    await _sweep_once()
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await _sweep_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover — defensive; keep the loop alive
            logger.exception("Scheduler tick failed")


def start(interval_seconds: Optional[int] = None) -> None:
    """Begin the periodic sweep. No-op when already running or disabled."""
    global _task
    seconds = interval_seconds if interval_seconds is not None else settings.sweep_interval_seconds
    if seconds <= 0:
        logger.info("Lifecycle sweep disabled (SWEEP_INTERVAL_SECONDS <= 0)")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop(seconds))
    logger.info("Lifecycle sweep scheduled every %s seconds", seconds)


async def stop() -> None:
    """Cancel the loop on shutdown so the process exits cleanly."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
