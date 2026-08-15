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


class UserAdminUpdate(BaseModel):
    """What an admin may change about ANOTHER user.

    Separate from UserUpdate (self-service) because role and farm assignment are
    exactly the fields a user must not be able to grant themselves.
    """
    name: Optional[str] = None
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    region: Optional[str] = None
    role: Optional[UserRole] = None
    # Activating a signed-up account. Signup writes false; this is the only
    # way it becomes true. See migration 0013.
    is_active: Optional[bool] = None
    # Which farm a Farm Manager belongs to. Meaningless for other roles, and
    # cleared automatically when the role changes away from `farm`.
    farm_id: Optional[UUID] = None


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
    # Resolved for display so an admin sees "Green Valley Dairy", not a UUID.
    farm_name: Optional[str] = None
    # False while a signed-up account waits for an admin to approve it.
    is_active: bool = True
    created_at: datetime
