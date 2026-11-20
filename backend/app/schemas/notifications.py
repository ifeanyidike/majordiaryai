from typing import Literal

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
    # A Yes / No question (questions.ANSWERERS): its answer once given, and
    # whether it still asks (unanswered, and not already done another way).
    answer: Optional[str] = None
    answered_at: Optional[datetime] = None
    asks: bool = False
    # Whether THIS caller is the one asked (questions.can_answer), so the app
    # shows Yes / No without its own copy of who answers what.
    can_answer: bool = False


class NotificationAnswer(BaseModel):
    answer: Literal["yes", "no"]
