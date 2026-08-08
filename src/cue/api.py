from __future__ import annotations

import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import func, select
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
from cue.discovery import apply_discovery_recipe, parse_document, parse_uploaded_document, song_list_json_schema
from cue.discovery_providers import fetch_billboard_hot_100, fetch_xmplaylist_recent
from cue.logging import configure_logging
from cue.models import (
    ApiToken,
    AuditEvent,
    CandidateAsset,
    Collection,
    CollectionEntry,
    CollectionResolution,
    CollectionVersion,
    Job,
    JobAttempt,
    LibraryImport,
    LibraryImportRow,
    PlaylistExport,
    SourceRow,
    SourceSnapshot,
    User,
)
from cue.services import (
    approve_library_import,
    approve_playlist_export,
    approve_snapshot,
    bootstrap_admin,
    create_collection,
    create_json_preview,
    create_library_import_preview,
    create_playlist_export_preview,
    queue_candidate_download,
    revoke_token,
    write_audit,
)
from cue.web import router as web_router

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


class JsonPreviewRequest(BaseModel):
    document: dict[str, Any] | list[Any]


class BillboardPreviewRequest(BaseModel):
    configured_source: str = Field(min_length=1, max_length=2048)
    chart_date: date | None = None


class XmplaylistPreviewRequest(BaseModel):
    station: str = Field(default="altnation", min_length=1, max_length=64)
    window_hours: int = Field(default=24, ge=1, le=24 * 30)


class CandidateSelectionRequest(BaseModel):
    collection_entry_id: int


class LibraryImportPreviewRequest(BaseModel):
    source_name: str | None = Field(default=None, max_length=255)


class PlaylistExportPreviewRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)


DEFAULT_LIBRARY_PAGE_SIZE = 100
MAX_LIBRARY_PAGE_SIZE = 500


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
    app.include_router(web_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz(request: Request) -> dict[str, str]:
        database_ready(request.app.state.engine)
        return {"status": "ready"}

    @app.get("/api/v1/song-list-schema")
    def get_song_list_schema() -> dict[str, object]:
        return song_list_json_schema()

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

    @app.post("/api/v1/collections/{collection_id}/json-previews", status_code=status.HTTP_201_CREATED)
    def post_json_preview(
        collection_id: int,
        payload: JsonPreviewRequest,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "collections:write")
        try:
            preview = parse_document(payload.document)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        with database_session(request) as session:
            collection = session.get(Collection, collection_id)
            if collection is None or collection.owner_id != principal.user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
            snapshot = create_json_preview(
                session,
                collection=collection,
                owner=principal.user,
                document=payload.document,
                preview=preview,
            )
            session.commit()
            return snapshot_summary(snapshot, preview.rows)

    @app.post("/api/v1/collections/{collection_id}/billboard-hot-100-previews", status_code=status.HTTP_201_CREATED)
    def post_billboard_hot_100_preview(
        collection_id: int,
        payload: BillboardPreviewRequest,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "collections:write")
        try:
            provider_document = fetch_billboard_hot_100(payload.configured_source, payload.chart_date)
        except ValueError as exc:
            record_provider_failure(request, principal.user, "billboard_hot_100", exc)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        with database_session(request) as session:
            collection = session.get(Collection, collection_id)
            if collection is None or collection.owner_id != principal.user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
            document = apply_discovery_recipe(provider_document.document, collection_recipe(session, collection.id))
            preview = parse_document(document)
            snapshot = create_json_preview(
                session,
                collection=collection,
                owner=principal.user,
                document=document,
                preview=preview,
                adapter="billboard_hot_100",
            )
            session.commit()
            return snapshot_summary(snapshot, preview.rows)

    @app.post("/api/v1/collections/{collection_id}/xmplaylist-previews", status_code=status.HTTP_201_CREATED)
    def post_xmplaylist_preview(
        collection_id: int,
        payload: XmplaylistPreviewRequest,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "collections:write")
        try:
            provider_document = fetch_xmplaylist_recent(payload.station, payload.window_hours)
        except ValueError as exc:
            record_provider_failure(request, principal.user, "xmplaylist_recent", exc)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        with database_session(request) as session:
            collection = session.get(Collection, collection_id)
            if collection is None or collection.owner_id != principal.user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
            document = apply_discovery_recipe(provider_document.document, collection_recipe(session, collection.id))
            preview = parse_document(document)
            snapshot = create_json_preview(
                session,
                collection=collection,
                owner=principal.user,
                document=document,
                preview=preview,
                adapter="xmplaylist_recent",
            )
            session.commit()
            return snapshot_summary(snapshot, preview.rows)

    @app.get("/api/v1/source-snapshots/{snapshot_id}")
    def get_snapshot(
        snapshot_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> dict[str, object]:
        require_scope(principal, "collections:read")
        with database_session(request) as session:
            snapshot = session.get(SourceSnapshot, snapshot_id)
            if snapshot is None or session.get(Collection, snapshot.collection_id).owner_id != principal.user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source snapshot not found")
            rows = list(session.scalars(select(SourceRow).where(SourceRow.snapshot_id == snapshot.id)))
            return snapshot_summary(snapshot, rows)

    @app.get("/api/v1/source-snapshots/{snapshot_id}/document")
    def download_snapshot_document(
        snapshot_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> Response:
        require_scope(principal, "collections:read")
        with database_session(request) as session:
            snapshot = session.get(SourceSnapshot, snapshot_id)
            if snapshot is None or session.get(Collection, snapshot.collection_id).owner_id != principal.user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source snapshot not found")
            return Response(
                content=snapshot.raw_document_json,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="cue-source-snapshot-{snapshot.id}.json"'},
            )

    @app.get("/api/v1/jobs")
    def list_jobs(
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> list[dict[str, object]]:
        require_scope(principal, "jobs:read")
        with database_session(request) as session:
            jobs = session.scalars(select(Job).where(Job.owner_id == principal.user.id).order_by(Job.id.desc()))
            return [job_summary(session, job) for job in jobs]

    @app.post("/api/v1/library-imports/previews", status_code=status.HTTP_201_CREATED)
    def post_library_import_preview(
        payload: LibraryImportPreviewRequest,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=MAX_LIBRARY_PAGE_SIZE)] = DEFAULT_LIBRARY_PAGE_SIZE,
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "collections:write")
        with database_session(request) as session:
            library_import = create_library_import_preview(
                session,
                owner=principal.user,
                media_root=request.app.state.settings.media_root,
                source_name=payload.source_name,
            )
            session.commit()
            return paginated_library_import_summary(session, library_import, page, page_size)

    @app.get("/api/v1/library-imports/{library_import_id}")
    def get_library_import(
        library_import_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=MAX_LIBRARY_PAGE_SIZE)] = DEFAULT_LIBRARY_PAGE_SIZE,
    ) -> dict[str, object]:
        require_scope(principal, "collections:read")
        with database_session(request) as session:
            library_import = session.get(LibraryImport, library_import_id)
            if library_import is None or library_import.owner_id != principal.user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library import not found")
            return paginated_library_import_summary(session, library_import, page, page_size)

    @app.get("/api/v1/library/assets")
    def list_library_assets(
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> list[dict[str, object]]:
        require_scope(principal, "collections:read")
        from cue.models import PublishedAsset, Recording

        with database_session(request) as session:
            rows = session.execute(
                select(PublishedAsset, Recording)
                .join(Recording, PublishedAsset.recording_id == Recording.id)
                .order_by(PublishedAsset.relative_path)
            ).all()
            return [
                {
                    "id": asset.id,
                    "recording_id": recording.id,
                    "artists": json.loads(recording.artists_json),
                    "title": recording.title,
                    "relative_path": asset.relative_path,
                    "container": asset.container,
                    "byte_size": asset.byte_size,
                    "source": "download" if asset.candidate_asset_id else "library_import",
                }
                for asset, recording in rows
            ]

    @app.post("/api/v1/collections/{collection_id}/playlist-export-previews", status_code=status.HTTP_201_CREATED)
    def post_playlist_export_preview(
        collection_id: int,
        payload: PlaylistExportPreviewRequest,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "collections:write")
        with database_session(request) as session:
            collection = session.get(Collection, collection_id)
            if collection is None or collection.owner_id != principal.user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
            try:
                playlist_export = create_playlist_export_preview(
                    session,
                    collection=collection,
                    owner=principal.user,
                    name=payload.name,
                    media_root=request.app.state.settings.media_root,
                    m3u_path_prefix=request.app.state.settings.m3u_path_prefix,
                )
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
            session.commit()
            return playlist_export_summary(playlist_export)

    @app.get("/api/v1/playlist-exports/{playlist_export_id}")
    def get_playlist_export(
        playlist_export_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> dict[str, object]:
        require_scope(principal, "collections:read")
        with database_session(request) as session:
            playlist_export = _owned_playlist_export(session, playlist_export_id, principal.user.id)
            return playlist_export_summary(playlist_export)

    @app.post("/api/v1/playlist-exports/{playlist_export_id}/approvals", status_code=status.HTTP_201_CREATED)
    def post_playlist_export_approval(
        playlist_export_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "collections:write")
        with database_session(request) as session:
            playlist_export = _owned_playlist_export(session, playlist_export_id, principal.user.id)
            try:
                job = approve_playlist_export(session, playlist_export, principal.user)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
            session.commit()
            return {"playlist_export_id": playlist_export.id, "status": playlist_export.status, "job_id": job.id}

    @app.get("/api/v1/playlist-exports/{playlist_export_id}/m3u8")
    def download_playlist_m3u8(
        playlist_export_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> FileResponse:
        require_scope(principal, "collections:read")
        with database_session(request) as session:
            playlist_export = _owned_playlist_export(session, playlist_export_id, principal.user.id)
            path = _export_artifact_path(request.app.state.settings.export_root, playlist_export.m3u8_relative_path)
        if path is None or not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="M3U8 export is not published")
        return FileResponse(path, media_type="application/x-mpegurl", filename=path.name)

    @app.get("/api/v1/playlist-exports/{playlist_export_id}/missing-report")
    def get_missing_report(
        playlist_export_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> dict[str, object]:
        require_scope(principal, "collections:read")
        with database_session(request) as session:
            playlist_export = _owned_playlist_export(session, playlist_export_id, principal.user.id)
            manifest = json.loads(playlist_export.manifest_json)
            return {"missing": manifest["missing"]}

    @app.post("/api/v1/library-imports/{library_import_id}/approvals")
    def post_library_import_approval(
        library_import_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "collections:write")
        with database_session(request) as session:
            library_import = session.get(LibraryImport, library_import_id)
            if library_import is None or library_import.owner_id != principal.user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library import not found")
            try:
                imported = approve_library_import(
                    session, library_import, principal.user, request.app.state.settings.media_root
                )
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
            session.commit()
            return {"library_import_id": library_import.id, "status": library_import.status, "imported": imported}

    @app.get("/api/v1/recordings/{recording_id}/candidates")
    def list_candidates(
        recording_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> list[dict[str, object]]:
        require_scope(principal, "collections:read")
        with database_session(request) as session:
            can_access = session.scalar(
                select(CollectionEntry.id)
                .join(CollectionVersion, CollectionEntry.collection_version_id == CollectionVersion.id)
                .join(Collection, CollectionVersion.collection_id == Collection.id)
                .where(CollectionEntry.recording_id == recording_id, Collection.owner_id == principal.user.id)
                .limit(1)
            )
            if can_access is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
            candidates = session.scalars(
                select(CandidateAsset)
                .where(CandidateAsset.recording_id == recording_id)
                .order_by(CandidateAsset.score.desc(), CandidateAsset.id)
            )
            return [
                {
                    "id": candidate.id,
                    "title": candidate.title,
                    "url": candidate.url,
                    "uploader": candidate.uploader,
                    "score": candidate.score,
                    "classifications": json.loads(candidate.classifications_json),
                    "reasons": json.loads(candidate.reasons_json),
                    "status": candidate.status,
                }
                for candidate in candidates
            ]

    @app.get("/api/v1/collections/{collection_id}/resolutions")
    def list_resolutions(
        collection_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(authenticate)],
    ) -> list[dict[str, object]]:
        require_scope(principal, "collections:read")
        with database_session(request) as session:
            collection = session.get(Collection, collection_id)
            if collection is None or collection.owner_id != principal.user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
            rows = session.execute(
                select(CollectionResolution, CollectionEntry)
                .join(CollectionEntry, CollectionResolution.collection_entry_id == CollectionEntry.id)
                .join(CollectionVersion, CollectionVersion.id == CollectionEntry.collection_version_id)
                .where(CollectionVersion.collection_id == collection.id)
                .order_by(CollectionEntry.ordinal)
            ).all()
            return [
                {
                    "id": resolution.id,
                    "collection_entry_id": entry.id,
                    "recording_id": entry.recording_id,
                    "status": resolution.status,
                    "candidate_id": resolution.candidate_asset_id,
                }
                for resolution, entry in rows
            ]

    @app.post("/api/v1/candidates/{candidate_id}/selections", status_code=status.HTTP_201_CREATED)
    def select_candidate(
        candidate_id: int,
        payload: CandidateSelectionRequest,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "collections:write")
        with database_session(request) as session:
            candidate = session.get(CandidateAsset, candidate_id)
            entry = session.get(CollectionEntry, payload.collection_entry_id)
            if candidate is None or entry is None or candidate.recording_id != entry.recording_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Candidate or collection entry not found"
                )
            owned = session.scalar(
                select(Collection.id)
                .join(CollectionVersion, CollectionVersion.collection_id == Collection.id)
                .where(CollectionVersion.id == entry.collection_version_id, Collection.owner_id == principal.user.id)
            )
            if owned is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Candidate or collection entry not found"
                )
            resolution = session.scalar(
                select(CollectionResolution).where(CollectionResolution.collection_entry_id == entry.id)
            )
            if resolution is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Candidate search has not completed")
            resolution.candidate_asset_id = candidate.id
            resolution.status = "selected"
            resolution.selected_by_id = principal.user.id
            resolution.selected_at = datetime.now(UTC).replace(tzinfo=None)
            candidate.status = "selected"
            job = queue_candidate_download(session, owner=principal.user, resolution=resolution)
            write_audit(
                session,
                actor_id=principal.user.id,
                action="candidate.selected",
                entity_type="candidate_asset",
                entity_id=candidate.id,
                detail={"collection_entry_id": entry.id, "job_id": job.id},
            )
            session.commit()
            return {"resolution_id": resolution.id, "status": resolution.status, "job_id": job.id}

    @app.post("/api/v1/jobs/{job_id}/retries")
    def retry_job(
        job_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "jobs:write")
        with database_session(request) as session:
            job = session.get(Job, job_id)
            if job is None or job.owner_id != principal.user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
            if job.status != "failed":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed jobs may be retried")
            job.status = "queued"
            job.claimed_at = None
            job.claimed_by = None
            write_audit(
                session,
                actor_id=principal.user.id,
                action="job.retried",
                entity_type="job",
                entity_id=job.id,
            )
            session.commit()
            return job_summary(session, job)

    @app.post("/api/v1/collections/{collection_id}/json-upload-previews", status_code=status.HTTP_201_CREATED)
    async def post_json_upload_preview(
        collection_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
        file: UploadFile = File(...),
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "collections:write")
        if not file.filename or not file.filename.lower().endswith(".json"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Upload a .json file")
        try:
            document = parse_uploaded_document(await file.read())
            preview = parse_document(document)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        with database_session(request) as session:
            collection = session.get(Collection, collection_id)
            if collection is None or collection.owner_id != principal.user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
            snapshot = create_json_preview(
                session,
                collection=collection,
                owner=principal.user,
                document=document,
                preview=preview,
            )
            session.commit()
            return snapshot_summary(snapshot, preview.rows)

    @app.post("/api/v1/source-snapshots/{snapshot_id}/approvals", status_code=status.HTTP_201_CREATED)
    def post_snapshot_approval(
        snapshot_id: int,
        request: Request,
        principal: Annotated[Principal, Depends(require_csrf)],
    ) -> dict[str, object]:
        require_administrator(request, principal)
        require_scope(principal, "collections:write")
        with database_session(request) as session:
            snapshot = session.get(SourceSnapshot, snapshot_id)
            if snapshot is None or session.get(Collection, snapshot.collection_id).owner_id != principal.user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source snapshot not found")
            try:
                job = approve_snapshot(session, snapshot, principal.user)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
            session.commit()
            return {"snapshot_id": snapshot.id, "status": snapshot.status, "job_id": job.id}

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


def snapshot_summary(snapshot: SourceSnapshot, rows: list[Any]) -> dict[str, object]:
    document = json.loads(snapshot.raw_document_json)
    provenance = document.get("provenance") if isinstance(document, dict) else None
    return {
        "id": snapshot.id,
        "collection_id": snapshot.collection_id,
        "status": snapshot.status,
        "adapter": snapshot.adapter,
        "source": snapshot.source_name,
        "source_url": snapshot.source_url,
        "provenance": provenance if isinstance(provenance, dict) else None,
        "counts": {state: sum(row.status == state for row in rows) for state in ("accepted", "duplicate", "rejected")},
        "rows": [
            {
                "position": row.position if hasattr(row, "position") else row.source_position,
                "rank": row.supplied_rank,
                "artists": row.artists if hasattr(row, "artists") else json.loads(row.artists_json or "[]"),
                "title": row.title,
                "status": row.status,
                "error": row.error,
            }
            for row in rows
        ],
    }


def collection_recipe(session: Session, collection_id: int) -> dict[str, Any]:
    version = session.scalar(
        select(CollectionVersion)
        .where(CollectionVersion.collection_id == collection_id)
        .order_by(CollectionVersion.version.desc())
    )
    return json.loads(version.recipe_json) if version is not None else {}


def record_provider_failure(request: Request, user: User, adapter: str, error: ValueError) -> None:
    with database_session(request) as session:
        write_audit(
            session,
            actor_id=user.id,
            action="provider.fetch_failed",
            entity_type="provider",
            entity_id=adapter,
            detail={"error": str(error)},
        )
        session.commit()


def job_summary(session: Session, job: Job) -> dict[str, object]:
    attempts = list(
        session.scalars(select(JobAttempt).where(JobAttempt.job_id == job.id).order_by(JobAttempt.attempt_number))
    )
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "last_error": job.last_error,
        "attempts": [
            {"number": attempt.attempt_number, "status": attempt.status, "error": attempt.error} for attempt in attempts
        ],
    }


def library_import_summary(library_import: LibraryImport, rows: list[LibraryImportRow]) -> dict[str, object]:
    states = ("accepted", "already_imported", "review", "imported")
    return {
        "id": library_import.id,
        "source_name": library_import.source_name,
        "status": library_import.status,
        "counts": {state: sum(row.status == state for row in rows) for state in states},
        "rows": [
            {
                "relative_path": row.relative_path,
                "byte_size": row.byte_size,
                "container": row.container,
                "artists": json.loads(row.artists_json) if row.artists_json else None,
                "title": row.title,
                "descriptor": row.descriptor,
                "year": row.year,
                "status": row.status,
                "error": row.error,
                "published_asset_id": row.published_asset_id,
            }
            for row in rows
        ],
    }


def paginated_library_import_summary(
    session: Session, library_import: LibraryImport, page: int, page_size: int
) -> dict[str, object]:
    states = ("accepted", "already_imported", "review", "imported")
    where = LibraryImportRow.library_import_id == library_import.id
    total_rows = session.scalar(select(func.count()).select_from(LibraryImportRow).where(where)) or 0
    state_counts = dict(
        session.execute(
            select(LibraryImportRow.status, func.count()).where(where).group_by(LibraryImportRow.status)
        ).all()
    )
    rows = list(
        session.scalars(
            select(LibraryImportRow)
            .where(where)
            .order_by(LibraryImportRow.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    summary = library_import_summary(library_import, rows)
    summary["counts"] = {state: state_counts.get(state, 0) for state in states}
    summary.update({"total_rows": total_rows, "page": page, "page_size": page_size})
    return summary


def playlist_export_summary(playlist_export: PlaylistExport) -> dict[str, object]:
    manifest = json.loads(playlist_export.manifest_json)
    return {
        "id": playlist_export.id,
        "collection_id": playlist_export.collection_id,
        "name": playlist_export.name,
        "status": playlist_export.status,
        "resolved_count": len(manifest["resolved"]),
        "missing_count": len(manifest["missing"]),
        "manifest": manifest,
        "digest": playlist_export.digest,
    }


def _owned_playlist_export(session: Session, playlist_export_id: int, owner_id: int) -> PlaylistExport:
    playlist_export = session.get(PlaylistExport, playlist_export_id)
    if playlist_export is None or playlist_export.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist export not found")
    return playlist_export


def _export_artifact_path(export_root: Path, name: str | None) -> Path | None:
    if not name or Path(name).name != name:
        return None
    return export_root / name


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
