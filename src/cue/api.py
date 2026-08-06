from __future__ import annotations

import json
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from cue.auth import (
    Principal,
    authenticate,
    issue_token,
    password_hash,
    require_administrator,
    require_csrf,
    require_scope,
)
from cue.config import Settings, get_settings
from cue.db import create_db_engine, database_ready, run_migrations
from cue.logging import configure_logging
from cue.models import ApiToken, AuditEvent, Collection, User
from cue.services import bootstrap_admin, create_collection, revoke_token, write_audit

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="src/cue/templates")


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=list)


class CollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    recipe: dict[str, object] = Field(default_factory=dict)


def database_session(request: Request) -> Session:
    return Session(request.app.state.engine)


def create_app(settings: Settings | None = None) -> FastAPI:
    configured_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(configured_settings.log_level)
        run_migrations(configured_settings)
        app.state.settings = configured_settings
        app.state.engine = create_db_engine(configured_settings)
        with Session(app.state.engine) as session:
            bootstrap_admin(
                session,
                configured_settings.bootstrap_admin_username,
                configured_settings.bootstrap_admin_password,
            )
        logger.info("Cue API started")
        yield
        app.state.engine.dispose()
        logger.info("Cue API stopped")

    app = FastAPI(title="Cue", version="0.1.0", lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=configured_settings.session_secret, https_only=True)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz(request: Request) -> dict[str, str]:
        database_ready(request.app.state.engine)
        return {"status": "ready"}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html", {"version": app.version})

    @app.post("/api/v1/auth/login")
    def login(payload: LoginRequest, request: Request) -> dict[str, object]:
        with database_session(request) as session:
            user = session.scalar(select(User).where(User.username == payload.username.strip()))
            if user is None or not user.is_active or not password_hash.verify(payload.password, user.password_hash):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            request.session.clear()
            request.session["user_id"] = user.id
            request.session["csrf_token"] = secrets.token_urlsafe(32)
            write_audit(
                session,
                actor_id=user.id,
                action="user.logged_in",
                entity_type="user",
                entity_id=user.id,
            )
            session.commit()
            return {"username": user.username, "csrf_token": request.session["csrf_token"]}

    @app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(request: Request, principal: Annotated[Principal, Depends(require_csrf)]) -> Response:
        with database_session(request) as session:
            write_audit(
                session,
                actor_id=principal.user.id,
                action="user.logged_out",
                entity_type="user",
                entity_id=principal.user.id,
            )
            session.commit()
        request.session.clear()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/v1/me")
    def me(principal: Annotated[Principal, Depends(authenticate)]) -> dict[str, object]:
        return {"id": principal.user.id, "username": principal.user.username}

    @app.post("/api/v1/tokens", status_code=status.HTTP_201_CREATED)
    def create_token(
        payload: TokenRequest,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "tokens:write")
        raw, prefix, token_hash = issue_token()
        with database_session(request) as session:
            token = ApiToken(
                user_id=principal.user.id,
                name=payload.name,
                token_prefix=prefix,
                token_hash=token_hash,
                scopes_json=json.dumps(sorted(set(payload.scopes))),
            )
            session.add(token)
            session.flush()
            write_audit(
                session,
                actor_id=principal.user.id,
                action="token.created",
                entity_type="api_token",
                entity_id=token.id,
                detail={"name": token.name, "scopes": payload.scopes},
            )
            session.commit()
            return {"id": token.id, "name": token.name, "token": raw, "scopes": payload.scopes}

    @app.delete("/api/v1/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_token(
        token_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
    ) -> Response:
        require_administrator(request, principal)
        require_scope(principal, "tokens:write")
        with database_session(request) as session:
            if not revoke_token(session, token_id, principal.user):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
            session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/v1/tokens")
    def list_tokens(
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> list[dict[str, object]]:
        require_administrator(request, principal)
        require_scope(principal, "tokens:read")
        with database_session(request) as session:
            tokens = session.scalars(
                select(ApiToken).where(ApiToken.user_id == principal.user.id).order_by(ApiToken.id)
            )
            return [
                {
                    "id": token.id,
                    "name": token.name,
                    "prefix": token.token_prefix,
                    "scopes": json.loads(token.scopes_json),
                    "revoked": token.revoked_at is not None,
                }
                for token in tokens
            ]

    @app.post("/api/v1/collections", status_code=status.HTTP_201_CREATED)
    def post_collection(
        payload: CollectionRequest,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "collections:write")
        with database_session(request) as session:
            collection = create_collection(session, principal.user, payload.name, payload.recipe)
            session.commit()
            return {"id": collection.id, "name": collection.name, "version": 1}

    @app.get("/api/v1/collections")
    def list_collections(
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> list[dict[str, object]]:
        require_scope(principal, "collections:read")
        with database_session(request) as session:
            collections = session.scalars(
                select(Collection).where(Collection.owner_id == principal.user.id).order_by(Collection.id)
            )
            return [{"id": item.id, "name": item.name} for item in collections]

    @app.get("/api/v1/audit-events")
    def list_audit_events(
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> list[dict[str, object]]:
        require_scope(principal, "audit:read")
        with database_session(request) as session:
            events = session.scalars(
                select(AuditEvent).where(AuditEvent.actor_id == principal.user.id).order_by(AuditEvent.id.desc())
            )
            return [
                {
                    "id": event.id,
                    "action": event.action,
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "detail": json.loads(event.detail_json),
                }
                for event in events
            ]

    return app


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
