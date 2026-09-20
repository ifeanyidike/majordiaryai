"""Alarms (owner -> technician) and Office Alerts (administrator -> technician).

Both feeds share one table and one set of endpoints, separated by `channel`.
What differs is who may write to each, which is enforced here AND in the RLS
policy added by migration 0015 -- the anon key ships inside the app, so the
database has to hold the same line the API does.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.models import Cow, Farm, Message, MessageChannel, User
from app.schemas.messages import MessageCreate, MessageOut, UnreadCounts
from app.services import messaging
from app.services.access import check_farm_access

router = APIRouter()

# Who may raise each feed. An owner cannot post an office alert -- the whole
# value of a separate feed is that its sender is known without reading it.
SENDER_ROLES = {
    MessageChannel.alarm: ("farm", "admin"),
    MessageChannel.office_alert: ("admin",),
}


def _out(message: Message, sender: Optional[User], farm: Optional[Farm],
         cow: Optional[Cow]) -> dict:
    return {
        **{c.key: getattr(message, c.key) for c in message.__table__.columns},
        "sender_name": sender.name if sender else None,
        "sender_role": sender.role.value if sender else None,
        "farm_name": farm.name if farm else None,
        "cow_label": cow.label if cow else None,
    }


async def _hydrate(db: AsyncSession, messages: List[Message]) -> List[dict]:
    """One query per lookup table rather than three per row."""
    if not messages:
        return []
    senders = {
        u.id: u for u in (await db.execute(
            select(User).where(User.id.in_({m.sender_id for m in messages}))
        )).scalars()
    }
    farm_ids = {m.farm_id for m in messages if m.farm_id}
    farms = {
        f.id: f for f in (await db.execute(
            select(Farm).where(Farm.id.in_(farm_ids))
        )).scalars()
    } if farm_ids else {}
    cow_ids = {m.cow_id for m in messages if m.cow_id}
    cows = {
        c.id: c for c in (await db.execute(
            select(Cow).where(Cow.id.in_(cow_ids))
        )).scalars()
    } if cow_ids else {}
    return [
        _out(m, senders.get(m.sender_id), farms.get(m.farm_id), cows.get(m.cow_id))
        for m in messages
    ]


@router.get("/", response_model=List[MessageOut])
async def list_messages(
    channel: MessageChannel = Query(..., description="alarm or office_alert"),
    unread_only: bool = False,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """This caller's feed. Admins see what they sent as well as what they were sent."""
    stmt = select(Message).where(Message.channel == channel)
    if current_user["role"] == "admin":
        stmt = stmt.where(
            (Message.recipient_id == current_user["id"])
            | (Message.sender_id == current_user["id"])
        )
    else:
        # A sender who is not an admin still sees their own outbox, which is
        # how an owner confirms the alarm actually went.
        stmt = stmt.where(
            (Message.recipient_id == current_user["id"])
            | (Message.sender_id == current_user["id"])
        )
    if unread_only:
        stmt = stmt.where(
            Message.read_at.is_(None), Message.recipient_id == current_user["id"]
        )
    stmt = stmt.order_by(Message.created_at.desc()).limit(max(1, min(limit, 500)))
    return await _hydrate(db, list((await db.execute(stmt)).scalars().all()))


@router.get("/unread-counts", response_model=UnreadCounts)
async def unread_counts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Both badges in one call — the dashboard shows them side by side."""
    rows = await db.execute(
        select(Message.channel, func.count())
        .where(Message.recipient_id == current_user["id"], Message.read_at.is_(None))
        .group_by(Message.channel)
    )
    counts = {channel: n for channel, n in rows.all()}
    return {
        "alarm": counts.get(MessageChannel.alarm, 0),
        "office_alert": counts.get(MessageChannel.office_alert, 0),
    }


@router.post("/", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_message(
    body: MessageCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    allowed = SENDER_ROLES[body.channel]
    if current_user["role"] not in allowed:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Only {' or '.join(allowed)} can post to the "
                f"{body.channel.value.replace('_', ' ')} feed"
            ),
        )

    farm_id = body.farm_id
    # A farm manager writes about their own farm whether or not they say so.
    if current_user["role"] == "farm":
        farm_id = current_user.get("farm_id")
        if farm_id is None:
            raise HTTPException(
                status_code=409, detail="Your account is not linked to a farm yet",
            )
    elif farm_id is not None and not await check_farm_access(db, current_user, farm_id):
        raise HTTPException(status_code=404, detail="Farm not found")

    recipient_id = body.recipient_id
    if recipient_id is None:
        if body.channel is not MessageChannel.alarm or farm_id is None:
            raise HTTPException(
                status_code=422,
                detail="recipient_id is required for this message",
            )
        recipient_id = await messaging.default_alarm_recipient(db, farm_id)
        if recipient_id is None:
            raise HTTPException(
                status_code=409,
                detail="This farm has no technician assigned — name a recipient",
            )
    if not await messaging.is_technician(db, recipient_id):
        raise HTTPException(
            status_code=422, detail="Messages can only be addressed to a technician",
        )

    if body.cow_id is not None:
        cow = await db.get(Cow, body.cow_id)
        if cow is None or (farm_id is not None and cow.farm_id != farm_id):
            raise HTTPException(status_code=422, detail="cow_id does not belong to this farm")

    message = await messaging.send(
        db, body.channel, current_user["id"], recipient_id, body.body,
        farm_id=farm_id, cow_id=body.cow_id,
    )
    await db.commit()
    await db.refresh(message)
    return (await _hydrate(db, [message]))[0]


@router.patch("/{message_id}/read", response_model=MessageOut)
async def mark_read(
    message_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Only the recipient can mark their own message read. Idempotent."""
    message = await db.get(Message, message_id)
    if message is None or message.recipient_id != current_user["id"]:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.read_at is None:
        message.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(message)
    return (await _hydrate(db, [message]))[0]
