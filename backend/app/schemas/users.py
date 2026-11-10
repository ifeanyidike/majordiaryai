from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
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


def sign_in_email(v: str) -> str:
    """A sign-in email, lower-cased. Unlike EmailStr it accepts the reserved
    .test domain: every test login is @majordairy.test, and an admin must be
    able to edit those accounts and add more of them for testing."""
    try:
        return validate_email(v.strip(), check_deliverability=False,
                              test_environment=True).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError(str(exc))


class TechnicianCreate(BaseModel):
    """Admin, Technicians, Add (feature notes, Nov 10). The admin sets a first
    password and gives it to the technician, who can change it with Forgot
    Password on the sign-in screen."""
    name: str = Field(min_length=1)
    email: str
    password: str = Field(min_length=8, max_length=72)
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    region: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name is required")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return sign_in_email(v)


class UserAdminUpdate(BaseModel):
    """What an admin may change about ANOTHER user.

    Separate from UserUpdate (self-service) because role and farm assignment are
    exactly the fields a user must not be able to grant themselves.
    """
    name: Optional[str] = None
    # Their sign-in email too: it is changed on the login as well as here.
    email: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: Optional[str]) -> Optional[str]:
        return sign_in_email(v) if v else None
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


class PushTokenBody(BaseModel):
    # An Expo push address, e.g. "ExponentPushToken[xxxxxxxx]".
    token: str = Field(min_length=10, max_length=300)
    platform: Optional[str] = Field(default=None, max_length=20)

    @field_validator("token")
    @classmethod
    def _is_expo_token(cls, v: str) -> str:
        # Anything else stored here would make Expo reject the whole batch it
        # is sent in, taking every other device's alarm down with it.
        if not (v.startswith(("ExponentPushToken[", "ExpoPushToken[")) and v.endswith("]")):
            raise ValueError("not an Expo push token")
        return v
