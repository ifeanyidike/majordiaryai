from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.models import UserRole


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: UserRole
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    region: Optional[str] = None
    farm_id: Optional[UUID] = None  # ignored on self-create; admin assigns via PATCH


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    region: Optional[str] = None


class UserOut(BaseModel):
    # Allow serialization straight from an ORM User object.
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    role: str
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    region: Optional[str] = None
    farm_id: Optional[UUID] = None
    created_at: datetime
