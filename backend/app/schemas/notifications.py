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
    created_at: datetime
