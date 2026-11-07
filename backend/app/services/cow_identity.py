"""Tags can repeat on a farm and the ID cannot, however an animal arrives.

Test results, Nov 5: "Allow the same tag on more than one animal", with the ID
telling them apart. Real herds reuse tags (migration 0022), but a tag already on
the farm is usually a typo, so it takes an "Are you sure?" and an ID.

The app reads the 409 by its opening words: src/app/cow/edit.tsx, and CalvingForm
in src/components/CowActionsSheet.tsx.
"""
import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Cow


async def refuse_an_id_in_use(db: AsyncSession, farm_id: uuid.UUID, herd_id: Optional[str]) -> None:
    """The ID is the number that stays unique on a farm (uq_cows_farm_id_herd_id).
    Said here, because the constraint can only answer with a generic failure."""
    if herd_id and await db.scalar(
        select(func.count(Cow.id)).where(Cow.farm_id == farm_id, Cow.herd_id == herd_id)
    ):
        raise HTTPException(status_code=409, detail=f"ID '{herd_id}' is already on this farm")


async def check_new_animal(db: AsyncSession, farm_id: uuid.UUID, ear_tag: Optional[str],
                           herd_id: Optional[str], allow_shared_tag: bool) -> None:
    """May a new animal take this tag and this ID?"""
    if ear_tag and await db.scalar(
        select(func.count(Cow.id)).where(Cow.farm_id == farm_id, Cow.ear_tag == ear_tag)
    ):
        if not allow_shared_tag:
            raise HTTPException(
                status_code=409,
                detail=f"Ear tag '{ear_tag}' already exists on this farm",
            )
        if not herd_id:
            raise HTTPException(
                status_code=422,
                detail="Another animal on this farm has this tag: give this one an ID",
            )
    await refuse_an_id_in_use(db, farm_id, herd_id)
