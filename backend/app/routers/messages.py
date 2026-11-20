"""Alarms (owner -> technician) and Office Alerts (administrator -> technician).

Both feeds share one table and one set of endpoints, separated by `channel`.
What differs is who may write to each, which is enforced here AND in the RLS
policy added by migration 0015 -- the anon key ships inside the app, so the
database has to hold the same line the API does.
"""

import uuid
from datetime import datetime, timedelta, timezone
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

# Who may post to each feed BY HAND. An owner cannot raise an office alert --
# the whole value of a separate feed is that its sender is known without
# reading it.
#
# The RLS policy (migration 0016) is deliberately one notch wider on
# office_alert: route-change alerts are raised automatically by whoever made
# the change, and a technician may hand off their own day. This table is the
# narrower gate, and it governs only what a person types.
SENDER_ROLES = {
    MessageChannel.alarm: ("farm", "admin"),
    MessageChannel.office_alert: ("admin",),
}


# Every alarm buzzes a phone. Nothing stopped an owner (or a stuck button)
# sending them back to back, and a technician whose phone rings twenty times
# in a minute learns to silence the channel -- which is the one that matters.
# Hand-written messages only: route-change alerts are raised by the system
# through messaging.send and never pass through here.
RATE_WINDOW = timedelta(minutes=10)
RATE_LIMIT = {
    MessageChannel.alarm: 5,
    MessageChannel.office_alert: 20,  # the office legitimately writes in bursts
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
    """This caller's feed: what they were sent, and what they sent."""
    # Inbox plus outbox, for everyone. The recipient needs the message; the
    # sender needs to see that it went, which is how an owner knows their
    # alarm was actually raised.
    received = Message.recipient_id == current_user["id"]
    if channel is MessageChannel.alarm:
        # An acknowledged alarm leaves the list of the person who received
        # it (Josh's change requests, Nov 20). The sender still sees it, and
        # that it was acknowledged.
        received = received & Message.acknowledged_at.is_(None)
    stmt = select(Message).where(
        Message.channel == channel,
        received | (Message.sender_id == current_user["id"]),
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
    # An alarm counts until it is acknowledged (Josh's change requests,
    # Nov 20: "Not yet" keeps it waiting); an office alert until it is read.
    rows = await db.execute(
        select(Message.channel, func.count())
        .where(
            Message.recipient_id == current_user["id"],
            ((Message.channel == MessageChannel.alarm) & Message.acknowledged_at.is_(None))
            | ((Message.channel == MessageChannel.office_alert) & Message.read_at.is_(None)),
        )
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

    # One send to the office is a row per admin, all stamped with the same
    # transaction time, so sends are counted by their distinct times.
    recent = await db.scalar(
        select(func.count(func.distinct(Message.created_at))).where(
            Message.sender_id == current_user["id"],
            Message.channel == body.channel,
            Message.created_at >= datetime.now(timezone.utc) - RATE_WINDOW,
        )
    )
    limit = RATE_LIMIT[body.channel]
    if recent >= limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You've sent {recent} in the last {int(RATE_WINDOW.total_seconds() // 60)} "
                "minutes — they have all been delivered. Please wait a few minutes "
                "before sending another."
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

    # A note is the farm's ordinary message on the Alarms feed (Josh's change
    # requests, Nov 20); an office alert is always the office's own kind.
    kind = body.kind if body.channel is MessageChannel.alarm else "alarm"

    if body.recipient_id is not None:
        # A farm names a technician only from their profile (Josh's change
        # requests, Nov 20), and only its own: before, any id was accepted.
        if current_user["role"] == "farm" and \
                body.recipient_id != await messaging.farm_technician(db, farm_id):
            raise HTTPException(
                status_code=422, detail="You can only write to your farm's technician",
            )
        recipients = [body.recipient_id]
    else:
        if body.channel is not MessageChannel.alarm or farm_id is None:
            raise HTTPException(
                status_code=422,
                detail="recipient_id is required for this message",
            )
        recipients = await messaging.alarm_recipients(db, farm_id, current_user["id"])
        if not recipients:
            raise HTTPException(
                status_code=409,
                detail="This farm has no technician and there is no office account to reach",
            )
    for recipient_id in recipients:
        if not await messaging.is_technician(db, recipient_id):
            raise HTTPException(
                status_code=422, detail="Messages can only be addressed to a technician",
            )

    if body.cow_id is not None:
        cow = await db.get(Cow, body.cow_id)
        if cow is None or (farm_id is not None and cow.farm_id != farm_id):
            raise HTTPException(status_code=422, detail="cow_id does not belong to this farm")

    # One send can be several rows (an alarm to the office reaches each admin).
    messages = [
        await messaging.send(
            db, body.channel, current_user["id"], recipient_id, body.body,
            farm_id=farm_id, cow_id=body.cow_id, kind=kind,
        )
        for recipient_id in recipients
    ]
    message = messages[0]
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


@router.post("/{message_id}/acknowledge", response_model=MessageOut)
async def acknowledge(
    message_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The recipient acknowledges an alarm or note: "I've seen it and I'll
    handle it" (Josh's change requests, Nov 20). It then leaves their list
    and their badge. Idempotent."""
    message = await db.get(Message, message_id, with_for_update=True)
    if message is None or message.recipient_id != current_user["id"]:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.channel is not MessageChannel.alarm:
        raise HTTPException(status_code=422, detail="Only an alarm or a note is acknowledged")
    if message.acknowledged_at is None:
        message.acknowledged_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(message)
    return (await _hydrate(db, [message]))[0]
