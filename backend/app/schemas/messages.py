from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.models import MessageChannel


class MessageCreate(BaseModel):
    channel: MessageChannel
    body: str = Field(min_length=1, max_length=2000)
    # Optional for an alarm: an owner writing from their own farm is answered
    # by that farm's standing technician. Required for an office alert, which
    # the administrator addresses deliberately.
    recipient_id: Optional[UUID] = None
    farm_id: Optional[UUID] = None
    cow_id: Optional[UUID] = None

    @field_validator("body")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        # min_length alone lets a body of spaces through, which then trips the
        # table's CHECK as a 500 instead of a 422.
        if not v.strip():
            raise ValueError("body cannot be blank")
        return v


class MessageOut(BaseModel):
    id: UUID
    channel: MessageChannel
    sender_id: UUID
    sender_name: Optional[str] = None
    sender_role: Optional[str] = None
    recipient_id: UUID
    farm_id: Optional[UUID] = None
    farm_name: Optional[str] = None
    cow_id: Optional[UUID] = None
    cow_label: Optional[str] = None
    body: str
    read_at: Optional[datetime] = None
    created_at: datetime


class UnreadCounts(BaseModel):
    """What the dashboard badges show without pulling either feed."""

    alarm: int
    office_alert: int
