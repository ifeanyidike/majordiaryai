"""Wake a phone when an Alarm or Office Alert arrives.

Messages were in-app only, so a farm owner raising "the cow in pen 4 is down"
reached the technician whenever he next opened the app. This sends each new
message to every device the recipient is signed in on, through Expo's push
service.

Same shape as the farm emails in notifications.py, for the same reasons:

  * queued on the session and sent only after COMMIT, so a message that rolls
    back never wakes anybody;
  * sent from a background task in its own session, so a slow or failing push
    service can never fail or delay the request that wrote the message;
  * best-effort and logged -- a push is a courtesy on top of the message,
    which is already saved and will be in the feed either way.

The decisions (which tokens, what payload, which tokens are dead) are pure
functions so they are testable without a network or a database.
"""

import asyncio
import logging
import uuid
from typing import Dict, Iterable, List, Optional, Sequence

import httpx
from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger("app.push")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
# Expo: "We recommend checking push receipts 15 minutes after sending"; they
# are cleared after 24 hours.
RECEIPT_DELAY_SECONDS = 15 * 60
# Receipt errors that mean OUR setup is broken, not one phone. These never
# appear in the immediate tickets, so without the receipt check a wrong or
# revoked Firebase key fails every alarm with nothing logged at all.
CREDENTIAL_ERRORS = {"InvalidCredentials", "MismatchSenderId"}
# Expo accepts at most 100 messages per request.
EXPO_BATCH = 100
# Android notification channels. The app creates both at start-up; an alarm
# rings at high importance, an office alert does not.
CHANNEL_FOR = {"alarm": "alarms", "office_alert": "office-alerts"}

_PENDING_KEY = "pending_pushes"
_bg_tasks: set = set()


def is_expo_token(token: str) -> bool:
    """Only Expo push addresses are ours to send to. Anything else in the table
    would be a client bug, and Expo would reject the whole batch for it."""
    return token.startswith(("ExponentPushToken[", "ExpoPushToken[")) and token.endswith("]")


def build_payloads(tokens: Sequence[str], title: str, body: str,
                   data: Dict, channel: str) -> List[Dict]:
    """One Expo message per device."""
    return [
        {
            "to": t,
            "title": title,
            "body": body if len(body) <= 180 else body[:177] + "…",
            "data": data,
            "sound": "default",
            # An alarm has to get through Doze on a phone left in a pocket.
            "priority": "high",
            "channelId": CHANNEL_FOR.get(channel, "default"),
        }
        for t in tokens if is_expo_token(t)
    ]


def dead_tokens(sent: Sequence[Dict], tickets: Sequence[Dict]) -> List[str]:
    """Tokens Expo says no longer reach a device (app uninstalled, signed out
    elsewhere). Tickets come back in the same order as the messages sent."""
    dead = []
    for message, ticket in zip(sent, tickets):
        details = ticket.get("details") or {}
        if ticket.get("status") == "error" and details.get("error") == "DeviceNotRegistered":
            dead.append(message["to"])
    return dead


def receipt_outcome(receipts: Dict[str, Dict], token_by_ticket: Dict[str, str]):
    """Read Expo's receipts: which tokens are gone, and what else went wrong.

    Returns (dead_tokens, problems) where problems maps each error code to how
    many receipts carried it.
    """
    dead, problems = [], {}
    for ticket_id, receipt in receipts.items():
        if receipt.get("status") != "error":
            continue
        code = (receipt.get("details") or {}).get("error") or "Unknown"
        problems[code] = problems.get(code, 0) + 1
        if code == "DeviceNotRegistered" and ticket_id in token_by_ticket:
            dead.append(token_by_ticket[ticket_id])
    return dead, problems


def queue_push(db: AsyncSession, user_id: uuid.UUID, title: str, body: str,
               data: Dict, channel: str) -> None:
    """Send after the surrounding transaction commits. The caller commits."""
    db.sync_session.info.setdefault(_PENDING_KEY, []).append(
        (user_id, title, body, data, channel)
    )


@event.listens_for(Session, "after_commit")
def _send_pending(session: Session) -> None:
    for item in session.info.pop(_PENDING_KEY, []):
        _schedule(*item)


@event.listens_for(Session, "after_rollback")
def _drop_pending(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)


def _schedule(user_id, title, body, data, channel) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # a sync script — no loop, no push
    task = loop.create_task(_deliver(user_id, title, body, data, channel))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _deliver(user_id, title, body, data, channel) -> None:
    from app.core.database import SessionLocal
    from app.models.models import PushToken

    try:
        async with SessionLocal() as session:
            tokens = list((await session.execute(
                select(PushToken.token).where(PushToken.user_id == user_id)
            )).scalars())
            if not tokens:
                # Not an error: he has not opened the new app yet, or denied
                # permission. The message is in his feed regardless.
                logger.info("No push token for user %s; message stays in-app", user_id)
                return

            payloads = build_payloads(tokens, title, body, data, channel)
            dead: List[str] = []
            token_by_ticket: Dict[str, str] = {}
            async with httpx.AsyncClient(timeout=10) as client:
                for i in range(0, len(payloads), EXPO_BATCH):
                    batch = payloads[i:i + EXPO_BATCH]
                    resp = await client.post(EXPO_PUSH_URL, json=batch)
                    if resp.status_code != 200:
                        logger.warning("Expo push rejected (%s): %s",
                                       resp.status_code, resp.text[:300])
                        continue
                    tickets = resp.json().get("data") or []
                    dead += dead_tokens(batch, tickets)
                    for message, ticket in zip(batch, tickets):
                        if ticket.get("status") == "ok" and ticket.get("id"):
                            token_by_ticket[ticket["id"]] = message["to"]

            await _prune(session, dead, user_id)
    except Exception:
        logger.exception("Push delivery failed for user %s", user_id)
        return

    if token_by_ticket:
        # Accepted is not delivered. Whether FCM/APNs actually took it -- and
        # whether our Firebase key even works -- is only in the receipts.
        await _check_receipts(user_id, token_by_ticket)


async def _prune(session, dead: List[str], user_id) -> None:
    from app.models.models import PushToken

    if not dead:
        return
    # Prune, or every future alarm to this user pays for a device that will
    # never answer.
    await session.execute(delete(PushToken).where(PushToken.token.in_(dead)))
    await session.commit()
    logger.info("Pruned %d dead push token(s) for user %s", len(dead), user_id)


async def _check_receipts(user_id, token_by_ticket: Dict[str, str]) -> None:
    """Best-effort: a restart during the wait loses this check, not the push."""
    from app.core.database import SessionLocal

    try:
        await asyncio.sleep(RECEIPT_DELAY_SECONDS)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(EXPO_RECEIPTS_URL, json={"ids": list(token_by_ticket)})
        if resp.status_code != 200:
            logger.warning("Expo receipts unavailable (%s)", resp.status_code)
            return
        dead, problems = receipt_outcome(resp.json().get("data") or {}, token_by_ticket)
        for code, n in problems.items():
            if code in CREDENTIAL_ERRORS:
                # Named for what it is, at ERROR: this is every alarm failing.
                logger.error(
                    "PUSH CREDENTIALS BROKEN: Expo reported %s on %d receipt(s) -- "
                    "the Firebase key uploaded to EAS is wrong or revoked; no "
                    "Android phone is receiving alarms", code, n)
            elif code != "DeviceNotRegistered":
                logger.warning("Push receipt error %s on %d message(s) for user %s",
                               code, n, user_id)
        if dead:
            async with SessionLocal() as session:
                await _prune(session, dead, user_id)
    except Exception:
        logger.exception("Push receipt check failed for user %s", user_id)
