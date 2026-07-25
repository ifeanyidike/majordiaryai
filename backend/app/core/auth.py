from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.config import settings
from app.core.database import get_db
import uuid

bearer_scheme = HTTPBearer()

# Supabase signs JWTs either with the legacy shared HS256 secret or, on newer
# projects, with rotating asymmetric keys (ES256/RS256) published at the JWKS
# endpoint. We support both. Asymmetric keys are cached by `kid` and refreshed
# on a cache miss (e.g. after a key rotation).
_JWKS_URL = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
_jwks_by_kid: dict = {}


async def _refresh_jwks() -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_JWKS_URL)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
    _jwks_by_kid.clear()
    for jwk in keys:
        kid = jwk.get("kid")
        if kid:
            _jwks_by_kid[kid] = jwk


async def _signing_key(kid: str) -> Optional[dict]:
    if kid not in _jwks_by_kid:
        try:
            await _refresh_jwks()
        except Exception:
            return None
    return _jwks_by_kid.get(kid)


async def _decode_token(token: str) -> dict:
    """Verify a Supabase JWT and return its claims with a parsed user id.

    Handles both HS256 (legacy shared secret) and ES256/RS256 (JWKS public
    keys). 401 on any failure.
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    alg = header.get("alg", settings.jwt_algorithm)
    options = {"verify_aud": False}
    try:
        if alg == "HS256":
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options=options)
        else:
            kid = header.get("kid")
            key = await _signing_key(kid) if kid else None
            if not key:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
            payload = jwt.decode(token, key, algorithms=[alg], options=options)

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        payload["user_id"] = uuid.UUID(user_id)
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload


async def get_token_claims(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """Token-only auth: verifies the JWT but does NOT require a users row.

    Used by /users/me (GET returns 404, POST creates) which runs before the
    profile row exists.
    """
    payload = await _decode_token(credentials.credentials)
    return {"id": payload["user_id"], "email": payload.get("email")}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    payload = await _decode_token(credentials.credentials)

    result = await db.execute(
        text(
            "SELECT id, name, email, role, phone, employee_id, region, farm_id, created_at "
            "FROM users WHERE id = :id"
        ),
        {"id": payload["user_id"]},
    )
    user = result.mappings().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return dict(user)


def require_roles(*roles: str):
    async def check(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    return check
