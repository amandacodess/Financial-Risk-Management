"""Accounts: password hashing, session tokens, and the current-user dependency.

Standard library only:
  * Passwords: scrypt (hashlib), a memory-hard KDF, with a random 16-byte salt
    per password. Stored as "scrypt$n$r$p$salt$hash" so parameters can change
    later without breaking old hashes.
  * Sessions: a random 256-bit token handed to the browser once. The database
    keeps only its SHA-256, so reading the sessions table does not give anyone
    a usable login.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request

from config import Config
from database import get_repo

_N, _R, _P = 2**14, 8, 1


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when the email is unknown, so a wrong email takes as long
# as a wrong password and response time does not reveal which accounts exist.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(repo, user_id: int, config: Config) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=config.session_days)
    repo.create_session(token_hash(token), user_id, expires)
    return token


def bearer_token(request: Request) -> str | None:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def current_user(request: Request, repo=Depends(get_repo)) -> dict:
    """The logged-in user, or 401. Every data route depends on this."""
    token = bearer_token(request)
    user = repo.get_session_user(token_hash(token)) if token else None
    if user is None:
        raise HTTPException(401, "Please log in to continue")
    return user


def user_id(user: dict = Depends(current_user)) -> int:
    return user["id"]
