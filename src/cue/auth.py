from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from cue.models import ApiToken, Role, User, UserRole

password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user: User
    token_scopes: frozenset[str] | None = None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token() -> tuple[str, str, str]:
    raw = f"cue_{secrets.token_urlsafe(32)}"
    return raw, raw[:12], hash_token(raw)


def get_session(request: Request) -> Session:
    return Session(request.app.state.engine)


def authenticate(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    with get_session(request) as session:
        if credentials and credentials.scheme.lower() == "bearer":
            token = session.scalar(
                select(ApiToken).where(
                    ApiToken.token_hash == hash_token(credentials.credentials),
                    ApiToken.revoked_at.is_(None),
                )
            )
            if token:
                user = session.get(User, token.user_id)
                if user and user.is_active:
                    return Principal(user, frozenset(json.loads(token.scopes_json)))
        user_id = request.session.get("user_id")
        if user_id:
            user = session.get(User, user_id)
            if user and user.is_active:
                return Principal(user)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


async def require_csrf(
    request: Request,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    principal: Principal = Depends(authenticate),
) -> Principal:
    if principal.token_scopes is not None:
        return principal
    expected = request.session.get("csrf_token")
    form_token = None
    if csrf_token is None:
        form = await request.form()
        form_token = form.get("csrf_token")
    token = csrf_token or form_token
    if not expected or not isinstance(token, str) or not secrets.compare_digest(expected, token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token required")
    return principal


def require_scope(principal: Principal, scope: str) -> None:
    if principal.token_scopes is None or "*" in principal.token_scopes or scope in principal.token_scopes:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Token scope {scope!r} required")


def require_administrator(request: Request, principal: Principal) -> None:
    with get_session(request) as session:
        has_role = session.scalar(
            select(UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == principal.user.id, Role.name == "administrator")
        )
    if has_role is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
