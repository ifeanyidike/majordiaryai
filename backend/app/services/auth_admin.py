"""Logins live in Supabase Auth; the users table holds the profile.

An admin adding a technician needs both: a login they can sign in with, and a
profile row under the same id. Signup cannot make one for them (it is the
technician's own phone that signs up), so the server does it with the service
key, the way scripts/create_test_users.py does.
"""
import logging
import uuid

import httpx

from app.core.config import settings

logger = logging.getLogger("app.auth_admin")


class LoginError(Exception):
    """Supabase refused. `taken` is set when the email already has a login."""

    def __init__(self, message: str, taken: bool = False):
        super().__init__(message)
        self.taken = taken


def _headers() -> dict:
    return {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "application/json",
    }


def _url(path: str = "") -> str:
    return f"{settings.supabase_url}/auth/v1/admin/users{path}"


def _refusal(resp: httpx.Response) -> LoginError:
    text = resp.text[:300]
    taken = resp.status_code in (400, 409, 422) and (
        "already" in text.lower() or "email_exists" in text)
    return LoginError(text, taken=taken)


async def _send(method: str, path: str = "", json: dict = None) -> httpx.Response:
    """One call to the admin API. Not reaching it is a refusal too, so callers
    answer the admin with "try again" instead of a server error."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            return await client.request(method, _url(path), headers=_headers(), json=json)
    except httpx.HTTPError as exc:
        raise LoginError(f"sign-in service unreachable: {exc!r}") from exc


async def create_login(email: str, password: str) -> uuid.UUID:
    """A login with the email already confirmed, so it works straight away."""
    resp = await _send("POST", json={"email": email, "password": password, "email_confirm": True})
    if resp.status_code not in (200, 201):
        raise _refusal(resp)
    return uuid.UUID(resp.json()["id"])


async def change_email(user_id: uuid.UUID, email: str) -> None:
    resp = await _send("PUT", f"/{user_id}", json={"email": email, "email_confirm": True})
    if resp.status_code not in (200, 201):
        raise _refusal(resp)


async def delete_login(user_id: uuid.UUID) -> None:
    """Undo a login whose profile could not be saved, so the email is free again."""
    resp = await _send("DELETE", f"/{user_id}")
    if resp.status_code not in (200, 204, 404):
        raise _refusal(resp)


async def undo(what: str, user_id: uuid.UUID, step) -> None:
    """Run an undo step after a failed save. If the undo fails too, the admin
    is still told what really went wrong, and the log says which login now
    disagrees with its profile, so it can be fixed by hand."""
    try:
        await step
    except LoginError as exc:
        logger.error("could not %s for login %s; fix it in Supabase Auth: %s", what, user_id, exc)
