"""Days already set for a technician who is losing a farm.

A farm's visit schedule can name someone for a single day (a
farm_visit_assignments row). When the farm moves to another technician, a day
from today on that still names the one losing it goes to the one taking it
(the user, Nov 10). Otherwise the old technician would still be sent there,
and that day would keep the farm open to them. A day given to anyone else, a
skipped day, and past days stay as they are.
"""

import uuid
from typing import Optional, Sequence

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import local_today
from app.models.models import FarmVisitAssignment


async def hand_over_days(
    db: AsyncSession,
    farm_ids: Sequence[uuid.UUID],
    old_technician_id: Optional[uuid.UUID],
    new_technician_id: Optional[uuid.UUID],
) -> None:
    """The caller commits. With no new technician the days are removed, not
    skipped: the farm has nobody, so no day can name anybody."""
    if old_technician_id is None or old_technician_id == new_technician_id or not farm_ids:
        return
    which = (
        FarmVisitAssignment.farm_id.in_(list(farm_ids)),
        FarmVisitAssignment.assigned_technician_id == old_technician_id,
        FarmVisitAssignment.visit_date >= local_today(),
    )
    if new_technician_id is None:
        await db.execute(delete(FarmVisitAssignment).where(*which))
    else:
        await db.execute(
            update(FarmVisitAssignment).where(*which)
            .values(assigned_technician_id=new_technician_id)
        )
