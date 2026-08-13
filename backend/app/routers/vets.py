from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.auth import get_current_user, require_roles
from app.models.models import Farm, Vet, VetFarmAssignment
from app.schemas.vets import VetCreate, VetOut, VetUpdate
from typing import List
import uuid

router = APIRouter()


@router.get("/", response_model=List[VetOut])
async def list_vets(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Vet).options(selectinload(Vet.farm_assignments)).order_by(Vet.name)
    )
    vets = result.scalars().all()
    return [
        {**{c.key: getattr(v, c.key) for c in v.__table__.columns},
         "farm_ids": [a.farm_id for a in v.farm_assignments]}
        for v in vets
    ]


@router.get("/{vet_id}", response_model=VetOut)
async def get_vet(
    vet_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Vet).where(Vet.id == vet_id).options(selectinload(Vet.farm_assignments))
    )
    vet = result.scalar_one_or_none()
    if not vet:
        raise HTTPException(status_code=404, detail="Vet not found")
    return {**{c.key: getattr(vet, c.key) for c in vet.__table__.columns},
            "farm_ids": [a.farm_id for a in vet.farm_assignments]}


@router.post("/", response_model=VetOut, status_code=status.HTTP_201_CREATED)
async def create_vet(
    body: VetCreate,
    current_user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    vet = Vet(**body.model_dump())
    db.add(vet)
    await db.commit()
    await db.refresh(vet)
    return {**{c.key: getattr(vet, c.key) for c in vet.__table__.columns}, "farm_ids": []}


@router.patch("/{vet_id}", response_model=VetOut)
async def update_vet(
    vet_id: uuid.UUID,
    body: VetUpdate,
    current_user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    vet = await db.get(Vet, vet_id)
    if not vet:
        raise HTTPException(status_code=404, detail="Vet not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "name" and value is None:
            continue  # name is non-nullable
        setattr(vet, field, value)
    await db.commit()

    result = await db.execute(
        select(Vet).where(Vet.id == vet_id).options(selectinload(Vet.farm_assignments))
    )
    vet = result.scalar_one()
    return {**{c.key: getattr(vet, c.key) for c in vet.__table__.columns},
            "farm_ids": [a.farm_id for a in vet.farm_assignments]}


@router.post("/{vet_id}/assign/{farm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def assign_farm(
    vet_id: uuid.UUID,
    farm_id: uuid.UUID,
    current_user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(Vet, vet_id):
        raise HTTPException(status_code=404, detail="Vet not found")
    if not await db.get(Farm, farm_id):
        raise HTTPException(status_code=404, detail="Farm not found")

    db.add(VetFarmAssignment(vet_id=vet_id, farm_id=farm_id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Vet is already assigned to this farm")


@router.delete("/{vet_id}/assign/{farm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_farm(
    vet_id: uuid.UUID,
    farm_id: uuid.UUID,
    current_user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(VetFarmAssignment).where(
            VetFarmAssignment.vet_id == vet_id,
            VetFarmAssignment.farm_id == farm_id,
        )
    )
    await db.commit()
