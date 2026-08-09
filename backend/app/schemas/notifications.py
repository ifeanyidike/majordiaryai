from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class NotificationOut(BaseModel):
    id: UUID
    farm_id: UUID
    cow_id: Optional[UUID] = None
    type: str
    message: str
    read: bool
    # Whether the farmer's email went out: sent | failed | no_email | disabled.
    # None on rows created before delivery tracking existed.
    email_status: Optional[str] = None
    emailed_at: Optional[datetime] = None
    created_at: datetime
