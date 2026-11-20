"""Notices that ask a Yes / No question (Josh's change requests, Nov 20).

  Day 223, to the farm:        "Cow [tag/name]: Day 223. Moved to dry pen?"
  Day 293, to the technician:  "Has cow [tag/name] given birth?"

The answer is stored on the notice. Each is asked once: Josh says nothing
about asking again, so a No is recorded and nothing more happens.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import local_today, to_local_date
from app.models.models import Cow, CowStatus, Notification
from app.services.notifications import create_notification

DRY_PEN_DAY = 223
BIRTH_CHECK_DAY = 293

# Which notice asks a question, and who may answer it: Josh names the farm for
# Day 223 and the technician for Day 293, and no one else.
# "dry_pen" is the Day 223 question; "dry_off" notices before Nov 20 told the
# farm to move her and asked nothing, so they stay statements.
ANSWERERS = {
    "dry_pen": ("farm",),
    "birth_check": ("technician",),
}
_STILL_CARRYING = (CowStatus.pregnant, CowStatus.dry)


def dry_pen_text(cow: Cow) -> str:
    return f"Cow {cow.label}: Day {DRY_PEN_DAY}. Moved to dry pen?"


def birth_check_text(cow: Cow) -> str:
    return f"Has cow {cow.label} given birth?"


def ask_dry_pen(db: AsyncSession, cow: Cow) -> Notification:
    return create_notification(db, cow.farm_id, cow.id, "dry_pen", dry_pen_text(cow))


def ask_birth_check(db: AsyncSession, cow: Cow) -> Notification:
    # For the technician alone: the farm is not asked, so not emailed.
    return create_notification(
        db, cow.farm_id, cow.id, "birth_check", birth_check_text(cow), email=False,
    )


def is_open(notice: Notification, cow: Optional[Cow]) -> bool:
    """Whether this notice still asks its question: unanswered, and the thing
    it asks about is not already done some other way."""
    if notice.type not in ANSWERERS or notice.answer is not None or cow is None:
        return False
    if notice.type == "dry_pen":
        return cow.status == CowStatus.dry and cow.dry_off_confirmed_date is None
    return cow.status in _STILL_CARRYING


def can_answer(notice: Notification, cow: Optional[Cow], role: str) -> bool:
    """Whether this person is the one asked, and the question is still open."""
    return role in ANSWERERS.get(notice.type, ()) and is_open(notice, cow)


def mark_moved_to_dry_pen(cow: Cow, today: date) -> None:
    """The dry cow is in the dry pen. Used by the farm's Yes and by the
    technician's confirm on the Dry Report, so both mean the same."""
    cow.dry_off_confirmed_date = today


def record_answer(notice: Notification, answer: str, user_id: uuid.UUID) -> None:
    notice.answer = answer
    notice.answered_at = datetime.now(timezone.utc)
    notice.answered_by_id = user_id


async def _latest_by_cow(db: AsyncSession, cow_ids, type_: str) -> dict:
    """The newest notice of this type for each cow, in one query."""
    if not cow_ids:
        return {}
    rows = (await db.execute(
        select(Notification)
        .where(Notification.cow_id.in_(cow_ids), Notification.type == type_)
        .order_by(Notification.cow_id, Notification.created_at.desc())
        .distinct(Notification.cow_id)
    )).scalars().all()
    return {n.cow_id: n for n in rows}


async def ask_birth_checks(
    db: AsyncSession,
    farm_ids: Optional[Iterable[uuid.UUID]] = None,
    today: Optional[date] = None,
) -> int:
    """Day 293 after insemination with no calving recorded: ask the
    technician, once for this breeding. The caller commits. Returns how many
    were asked."""
    today = today or local_today()
    farm_ids = list(farm_ids) if farm_ids is not None else None
    if farm_ids is not None and not farm_ids:
        return 0
    stmt = select(Cow).where(
        Cow.status.in_(_STILL_CARRYING),
        Cow.last_insemination_date <= today - timedelta(days=BIRTH_CHECK_DAY),
    )
    if farm_ids is not None:
        stmt = stmt.where(Cow.farm_id.in_(farm_ids))
    cows = (await db.execute(stmt.order_by(Cow.id))).scalars().all()
    latest = await _latest_by_cow(db, [c.id for c in cows], "birth_check")
    made = 0
    for cow in cows:
        last = latest.get(cow.id)
        # One from before this breeding belongs to an earlier pregnancy.
        if last is None or to_local_date(last.created_at) < cow.last_insemination_date:
            ask_birth_check(db, cow)
            made += 1
    return made
