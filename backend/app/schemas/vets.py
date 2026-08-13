from pydantic import BaseModel, EmailStr
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class VetCreate(BaseModel):
    name: str
    clinic: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    user_id: Optional[UUID] = None


class VetUpdate(BaseModel):
    name: Optional[str] = None
    clinic: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    user_id: Optional[UUID] = None


class VetOut(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    name: str
    clinic: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    created_at: datetime
    farm_ids: List[UUID] = []
