"""Transactional email via SendGrid.

Reusable across the app (notifications now, invites later). Sends through the
SendGrid v3 REST API using httpx (no extra dependency). Safely no-ops and logs
when SENDGRID_API_KEY is unset, so nothing breaks before the key is configured.
"""

import logging
import re
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("app.email")

_SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
_TAG_RE = re.compile(r"<[^>]+>")


def _to_text(html: str) -> str:
    """Very small HTML → plain-text fallback for the text/plain part."""
    return _TAG_RE.sub("", html).strip()


def is_configured() -> bool:
    return bool(settings.sendgrid_api_key)


async def send_email(to: str, subject: str, html: str, text: Optional[str] = None) -> bool:
    """Send one email. Returns True on success, False on any failure/disabled.

    Never raises — email must not break the flow that triggered it.
    """
    if not settings.sendgrid_api_key:
        logger.info("Email disabled (SENDGRID_API_KEY unset) — skipped: to=%s subject=%r", to, subject)
        return False
    if not to:
        return False

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": settings.email_from, "name": settings.email_from_name},
        "subject": subject,
        # SendGrid requires text/plain before text/html.
        "content": [
            {"type": "text/plain", "value": text or _to_text(html)},
            {"type": "text/html", "value": html},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _SENDGRID_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
            )
        if resp.status_code >= 400:
            logger.error("SendGrid %s sending to %s: %s", resp.status_code, to, resp.text[:300])
            return False
        return True
    except Exception:
        logger.exception("SendGrid request failed (to=%s)", to)
        return False
