"""Protocol completion, insemination fold-in, bleeding and abandonment.

The query tests (test_worklists.py) prove membership; these prove the state
MUTATIONS that move a cow between reports. Every one of them corresponds to a
way a cow could previously end up on no report at all, or to work that could
not be recorded.

They drive the real service functions, not re-implementations.
"""

from datetime import date

import pytest

from app.core.timeutils import local_today
from sqlalchemy import select

from app.models.models import (
    CowStatus, EnrollmentStatus, NeedlingEnrollment, ProtocolType,
)
from app.services import status_engine
from app.services.worklists import (
    injection_only, latest_open_record_stmt, needling_due_stmt,
    pending_final_record_stmt, timed_breeding_stmt,
)

# The app computes 'today' in the farm timezone; using the machine's
# UTC date made boundary tests flake on CI between 00:00 and 04:00.
TODAY = local_today()

FINAL_TODAY = (10, 0, "2cc GnRH + Insemination", True, False)
PGF_FINAL_TODAY = (5, 0, "Heat Observation + Insemination if in heat", True, False)


async def enrollment_of(db, cow) -> NeedlingEnrollment:
    return await db.scalar(
        select(NeedlingEnrollment).where(NeedlingEnrollment.cow_id == cow.id)
    )


async def on_needling(db, cow):
    rows = (await db.execute(needling_due_stmt(TODAY))).all()
    return [r for r, c in rows if c.id == cow.id]


async def on_timed_breeding(db, cow):
    rows = (await db.execute(timed_breeding_stmt(TODAY))).all()
    return [rec for rec, enr, c, farm in rows if c.id == cow.id]


# ── Completing the last scheduled step ───────────────────────────────

async def test_timed_ai_final_step_leaves_cow_awaiting_ai(db, make_cow):
    """Ovsynch day 10: the shot is given, the AI is not. She must stay visible."""
    cow = await make_cow(steps=[FINAL_TODAY])
    enrollment = await enrollment_of(db, cow)

    await status_engine.on_final_record_completed(cow, enrollment, db)
    await db.flush()

    assert enrollment.status == EnrollmentStatus.completed_pending_ai
    assert cow.status == CowStatus.needling
    assert len(await on_timed_breeding(db, cow)) == 1, "cow awaiting AI vanished"


async def test_pgf_heat_final_step_returns_cow_to_open(db, make_cow):
    """PGF Heat's last day is observation, not timed AI. Marking it complete
    used to set `completed_pending_ai` on a protocol Timed Breeding excludes —
    dead-ending the cow on no report, in `needling` status, forever."""
    cow = await make_cow(protocol=ProtocolType.prostaglandin_heat, steps=[PGF_FINAL_TODAY])
    enrollment = await enrollment_of(db, cow)

    await status_engine.on_final_record_completed(cow, enrollment, db)
    await db.flush()

    assert enrollment.status == EnrollmentStatus.completed
    assert cow.status == CowStatus.open, "PGF-heat cow dead-ended in needling status"
    assert cow.current_program is None
    assert not await on_needling(db, cow)
    assert not await on_timed_breeding(db, cow)


async def test_final_step_on_drifted_cow_is_rejected_not_forced(db, make_cow):
    """The status write goes through the same guard as every other one."""
    # dry -> open is not a legal transition; pregnant -> open is, so it would
    # not exercise the guard.
    cow = await make_cow(protocol=ProtocolType.prostaglandin_heat,
                         cow_status=CowStatus.dry, steps=[PGF_FINAL_TODAY])
    enrollment = await enrollment_of(db, cow)

    with pytest.raises(Exception) as exc:
        await status_engine.on_final_record_completed(cow, enrollment, db)
    assert "Illegal status transition" in str(exc.value)


# ── Insemination folds in the final record ───────────────────────────

async def test_insemination_closes_pending_final_record(db, make_cow):
    cow = await make_cow(steps=[FINAL_TODAY])
    record = await db.scalar(pending_final_record_stmt(cow.id, TODAY))
    assert record is not None and not record.completed


async def test_backdated_insemination_still_finds_the_record(db, make_cow):
    """Gating the lookup on the AI's own date orphaned the record whenever a
    technician entered yesterday's insemination."""
    cow = await make_cow(steps=[(10, -2, "2cc GnRH + Insemination", True, False)])
    # The AI is recorded as having happened two days ago; the record is older
    # still. `today` is what bounds the lookup, not the AI date.
    record = await db.scalar(pending_final_record_stmt(cow.id, TODAY))
    assert record is not None, "back-dated AI would orphan the final injection"


async def test_future_final_step_is_not_marked_given(db, make_cow):
    cow = await make_cow(steps=[(10, 3, "2cc GnRH + Insemination", True, False)])
    assert await db.scalar(pending_final_record_stmt(cow.id, TODAY)) is None


async def test_pgf_heat_final_record_closes_on_insemination(db, make_cow):
    """Heat observed on day 5 → AI recorded. The record must close regardless of
    whether the technician tapped "complete" first, or the outcome depended on
    tap order."""
    cow = await make_cow(protocol=ProtocolType.prostaglandin_heat, steps=[PGF_FINAL_TODAY])
    record = await db.scalar(pending_final_record_stmt(cow.id, TODAY))
    assert record is not None, "conditional-AI protocols were skipped by the fold-in"


# ── Bleeding, recordable on any day ──────────────────────────────────

async def test_bleeding_reachable_when_final_shot_already_given(db, make_cow):
    """After the final injection there is no completable record left, so routing
    bleeding through "complete this record" made it unrecordable exactly when
    the cow is closest to insemination. The standalone path still finds her."""
    cow = await make_cow(
        enrollment_status=EnrollmentStatus.completed_pending_ai,
        steps=[(10, 0, "2cc GnRH + Insemination", True, True)],
    )
    # No open record to attach to — and that must not block the event.
    assert await db.scalar(latest_open_record_stmt(cow.id)) is None

    await status_engine.on_bleeding_before_insemination(cow, db)
    await db.flush()

    assert cow.status == CowStatus.needling  # re-enrolled on Ovsynch
    assert cow.current_program == ProtocolType.ovsynch.value
    enrollments = (await db.execute(
        select(NeedlingEnrollment).where(NeedlingEnrollment.cow_id == cow.id)
    )).scalars().all()
    assert any(e.status == EnrollmentStatus.cancelled for e in enrollments)
    assert any(e.status == EnrollmentStatus.active for e in enrollments)


async def test_bleeding_attaches_to_an_open_record_when_there_is_one(db, make_cow):
    cow = await make_cow(steps=[(7, 0, "2cc PGF", False, False)])
    record = await db.scalar(latest_open_record_stmt(cow.id))
    assert record is not None and record.protocol_day == 7


# ── Abandoned protocols ──────────────────────────────────────────────

async def test_abandoned_final_day_is_cancelled_and_cow_returns_to_open(db, make_cow):
    """An un-actioned final record pinned the cow on Timed Breeding forever AND
    suppressed every other injection she was due."""
    cow = await make_cow(steps=[(10, -(status_engine.ABANDONED_PROTOCOL_DAYS + 1),
                                 "2cc GnRH + Insemination", True, False)])
    assert len(await on_timed_breeding(db, cow)) == 1  # stuck there before the sweep

    changed = await status_engine._expire_stale_enrollments(db, None, TODAY)
    await db.flush()

    assert changed == 1
    assert cow.status == CowStatus.open
    assert not await on_timed_breeding(db, cow)
    assert not await on_needling(db, cow)


def test_abandonment_window_is_the_two_days_the_client_answered():
    """SPEC_QUESTIONS.md Q2, "how long before we cancel the program?" ->
    "2. Goes to open status". Two days, then Open. It shipped as 7 (a guess),
    and the difference is five days of a cow sitting on Timed Breeding with
    every other injection she is due suppressed behind her."""
    assert status_engine.ABANDONED_PROTOCOL_DAYS == 2


async def test_recently_overdue_final_day_is_left_alone(db, make_cow):
    """Overdue by a day is normal — only a lapsed protocol gets cancelled."""
    cow = await make_cow(steps=[(10, -1, "2cc GnRH + Insemination", True, False)])
    changed = await status_engine._expire_stale_enrollments(db, None, TODAY)
    assert changed == 0
    assert cow.status == CowStatus.needling
    assert len(await on_timed_breeding(db, cow)) == 1


async def test_actively_worked_protocol_is_not_expired(db, make_cow):
    """A technician catching up on late shots is not abandonment: any record
    completed inside the abandonment window keeps the enrollment alive, even
    when the final day itself is long past."""
    from datetime import timedelta

    from app.models.models import NeedlingRecord

    stale = status_engine.ABANDONED_PROTOCOL_DAYS + 3
    cow = await make_cow(steps=[(10, -stale, "2cc GnRH + Insemination", True, False)])
    # A shot given yesterday — somebody is clearly still working this cow.
    db.add(NeedlingRecord(
        enrollment_id=cow.enrollment.id, cow_id=cow.id,
        protocol_day=7, scheduled_date=TODAY - timedelta(days=stale + 3),
        treatment="2cc PGF", is_final=False,
        completed=True, completed_date=TODAY - timedelta(days=1),
    ))
    await db.flush()

    changed = await status_engine._expire_stale_enrollments(db, None, TODAY)
    assert changed == 0, "expired an enrollment with a shot given yesterday"
    assert cow.status == CowStatus.needling

    # Once the recent work ages out past the cutoff, expiry applies again.
    later = TODAY + timedelta(days=status_engine.ABANDONED_PROTOCOL_DAYS + 2)
    changed = await status_engine._expire_stale_enrollments(db, None, later)
    assert changed == 1
    assert cow.status == CowStatus.open


@pytest.mark.parametrize("days,has_signal,accepted", [
    (2, True, False),    # metestrous spotting right after breeding — NOT a returned heat
    (19, True, False),   # still before the window opens
    (20, True, True),
    (27, True, True),    # late return to heat / blood on tail — recordable
    (60, True, True),    # any day until a pregnancy result
    (20, False, True),
    (25, False, True),
    (19, False, False),  # routine checks stay window-bound
    (26, False, False),
])
def test_heat_check_timing_rule(days, has_signal, accepted):
    error = status_engine.heat_check_timing_error(days, has_signal=has_signal)
    assert (error is None) is accepted, error


# ── Display strings ──────────────────────────────────────────────────

@pytest.mark.parametrize("treatment,expected", [
    ("2cc GnRH + Insemination", "2cc GnRH"),
    ("2cc PGF", "2cc PGF"),
    ("", None),
    (None, None),
])
def test_injection_only_strips_the_insemination_clause(treatment, expected):
    """Without this the row read "Give final 2cc GnRH + Insemination +
    inseminate today"."""
    assert injection_only(treatment) == expected
