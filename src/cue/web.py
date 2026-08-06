from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from cue.auth import Principal, password_hash, require_csrf
from cue.discovery import parse_document
from cue.models import (
    CandidateAsset,
    Collection,
    CollectionEntry,
    CollectionResolution,
    LibraryImport,
    LibraryImportRow,
    PlaylistExport,
    Recording,
    SourceRow,
    SourceSnapshot,
    User,
)
from cue.services import (
    approve_library_import,
    approve_playlist_export,
    approve_snapshot,
    create_collection,
    create_json_preview,
    create_library_import_preview,
    create_playlist_export_preview,
    get_download_batch_size,
    queue_candidate_download,
    set_download_batch_size,
    write_audit,
)

templates = Jinja2Templates(directory="src/cue/templates")
router = APIRouter(include_in_schema=False)


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def current_user(request: Request, session: Session) -> User | None:
    user_id = request.session.get("user_id")
    return session.get(User, user_id) if isinstance(user_id, int) else None


def require_web_user(request: Request, session: Session) -> User:
    user = current_user(request, session)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


def render(request: Request, name: str, **context: object) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        name,
        {
            "csrf_token": request.session.get("csrf_token"),
            "flash": request.session.pop("flash", None),
            **context,
        },
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    if request.session.get("user_id"):
        return redirect("/")
    return render(request, "login.html", title="Sign in")


@router.post("/login")
def login_form(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = session.scalar(select(User).where(User.username == username.strip()))
        if user is None or not user.is_active or not password_hash.verify(password, user.password_hash):
            request.session["flash"] = ("error", "Invalid username or password.")
            return redirect("/login")
        request.session.clear()
        request.session["user_id"] = user.id
        request.session["csrf_token"] = secrets.token_urlsafe(32)
        write_audit(session, actor_id=user.id, action="user.logged_in", entity_type="user", entity_id=user.id)
        session.commit()
    return redirect("/")


@router.post("/logout")
def logout_form(request: Request, _: Annotated[Principal, Depends(require_csrf)]) -> RedirectResponse:
    request.session.clear()
    return redirect("/login")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    with Session(request.app.state.engine) as session:
        user = current_user(request, session)
        if user is None:
            return redirect("/login")
        collections = list(
            session.scalars(select(Collection).where(Collection.owner_id == user.id).order_by(Collection.id.desc()))
        )
        assets = len(list(session.scalars(select(Recording.id))))
        reviews = len(
            list(session.scalars(select(CollectionResolution.id).where(CollectionResolution.status == "review")))
        )
        from cue.models import Job

        queued = len(list(session.scalars(select(Job.id).where(Job.owner_id == user.id, Job.status == "queued"))))
        failed = len(list(session.scalars(select(Job.id).where(Job.owner_id == user.id, Job.status == "failed"))))
        return render(
            request,
            "dashboard.html",
            title="Dashboard",
            user=user,
            collections=collections,
            stats={"recordings": assets, "review": reviews, "queued": queued, "failed": failed},
        )


@router.post("/collections")
def create_collection_form(
    request: Request,
    name: Annotated[str, Form()],
    _: Annotated[Principal, Depends(require_csrf)],
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        collection = create_collection(session, user, name, {})
        collection_id = collection.id
        session.commit()
    return redirect(f"/collections/{collection_id}")


@router.get("/collections/{collection_id}", response_class=HTMLResponse)
def collection_page(collection_id: int, request: Request) -> HTMLResponse:
    with Session(request.app.state.engine) as session:
        user = current_user(request, session)
        if user is None:
            return redirect("/login")
        collection = session.get(Collection, collection_id)
        if collection is None or collection.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Collection not found")
        snapshots = list(
            session.scalars(
                select(SourceSnapshot)
                .where(SourceSnapshot.collection_id == collection.id)
                .order_by(SourceSnapshot.id.desc())
            )
        )
        latest = next((snapshot for snapshot in snapshots if snapshot.status == "approved"), None)
        items: list[dict[str, object]] = []
        if latest:
            rows = session.execute(
                select(CollectionEntry, Recording, CollectionResolution)
                .join(Recording, CollectionEntry.recording_id == Recording.id)
                .join(SourceRow, CollectionEntry.source_row_id == SourceRow.id)
                .outerjoin(CollectionResolution, CollectionResolution.collection_entry_id == CollectionEntry.id)
                .where(SourceRow.snapshot_id == latest.id)
                .order_by(CollectionEntry.ordinal)
            ).all()
            for entry, recording, resolution in rows:
                candidates = list(
                    session.scalars(
                        select(CandidateAsset)
                        .where(CandidateAsset.recording_id == recording.id)
                        .order_by(CandidateAsset.score.desc())
                    )
                )
                items.append(
                    {
                        "entry": entry,
                        "recording": recording,
                        "resolution": resolution,
                        "candidates": candidates,
                    }
                )
        return render(
            request,
            "collection.html",
            title=collection.name,
            user=user,
            collection=collection,
            snapshots=snapshots,
            latest=latest,
            items=items,
        )


@router.post("/collections/{collection_id}/exports")
def playlist_export_preview_form(
    collection_id: int, request: Request, _: Annotated[Principal, Depends(require_csrf)]
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        collection = session.get(Collection, collection_id)
        if collection is None or collection.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Collection not found")
        playlist_export = create_playlist_export_preview(
            session,
            collection=collection,
            owner=user,
            name=None,
            media_root=request.app.state.settings.media_root,
            m3u_path_prefix=request.app.state.settings.m3u_path_prefix,
        )
        playlist_export_id = playlist_export.id
        session.commit()
    return redirect(f"/exports/{playlist_export_id}")


@router.get("/exports/{playlist_export_id}", response_class=HTMLResponse)
def playlist_export_page(playlist_export_id: int, request: Request) -> HTMLResponse:
    with Session(request.app.state.engine) as session:
        user = current_user(request, session)
        if user is None:
            return redirect("/login")
        playlist_export = session.get(PlaylistExport, playlist_export_id)
        if playlist_export is None or playlist_export.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Playlist export not found")
        return render(
            request,
            "playlist_export.html",
            title="Playlist export",
            user=user,
            playlist_export=playlist_export,
            manifest=json.loads(playlist_export.manifest_json),
        )


@router.post("/exports/{playlist_export_id}/approve")
def approve_playlist_export_form(
    playlist_export_id: int, request: Request, _: Annotated[Principal, Depends(require_csrf)]
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        playlist_export = session.get(PlaylistExport, playlist_export_id)
        if playlist_export is None or playlist_export.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Playlist export not found")
        approve_playlist_export(session, playlist_export, user)
        session.commit()
    return redirect(f"/exports/{playlist_export_id}")


@router.post("/collections/{collection_id}/json-previews")
def json_preview_form(
    collection_id: int,
    request: Request,
    document: Annotated[str, Form()],
    _: Annotated[Principal, Depends(require_csrf)],
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        collection = session.get(Collection, collection_id)
        if collection is None or collection.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Collection not found")
        try:
            payload = json.loads(document)
            snapshot = create_json_preview(
                session, collection=collection, owner=user, document=payload, preview=parse_document(payload)
            )
            session.commit()
            request.session["flash"] = ("success", f"Created preview #{snapshot.id}.")
        except (ValueError, json.JSONDecodeError) as exc:
            request.session["flash"] = ("error", f"JSON was not accepted: {exc}")
    return redirect(f"/collections/{collection_id}")


@router.post("/snapshots/{snapshot_id}/approve")
def approve_snapshot_form(
    snapshot_id: int, request: Request, _: Annotated[Principal, Depends(require_csrf)]
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        snapshot = session.get(SourceSnapshot, snapshot_id)
        if snapshot is None or session.get(Collection, snapshot.collection_id).owner_id != user.id:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        try:
            approve_snapshot(session, snapshot, user)
            session.commit()
        except ValueError as exc:
            request.session["flash"] = ("error", str(exc))
        return redirect(f"/collections/{snapshot.collection_id}")


@router.post("/candidates/{candidate_id}/select")
def select_candidate_form(
    candidate_id: int,
    request: Request,
    entry_id: Annotated[int, Form()],
    _: Annotated[Principal, Depends(require_csrf)],
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        candidate, entry = session.get(CandidateAsset, candidate_id), session.get(CollectionEntry, entry_id)
        if candidate is None or entry is None or candidate.recording_id != entry.recording_id:
            raise HTTPException(status_code=404, detail="Candidate not found")
        resolution = session.scalar(
            select(CollectionResolution).where(CollectionResolution.collection_entry_id == entry.id)
        )
        if resolution is None:
            raise HTTPException(status_code=409, detail="Candidate search has not completed")
        resolution.candidate_asset_id, resolution.status = candidate.id, "selected"
        resolution.selected_by_id = user.id
        resolution.selected_at = datetime.now(UTC).replace(tzinfo=None)
        candidate.status = "selected"
        queue_candidate_download(session, owner=user, resolution=resolution)
        session.commit()
        source_row = session.get(SourceRow, entry.source_row_id)
        snapshot = session.get(SourceSnapshot, source_row.snapshot_id) if source_row else None
        return redirect(f"/collections/{snapshot.collection_id}" if snapshot else "/")


@router.get("/library", response_class=HTMLResponse)
def library_page(request: Request) -> HTMLResponse:
    with Session(request.app.state.engine) as session:
        user = current_user(request, session)
        if user is None:
            return redirect("/login")
        imports = list(
            session.scalars(
                select(LibraryImport).where(LibraryImport.owner_id == user.id).order_by(LibraryImport.id.desc())
            )
        )
        return render(request, "library.html", title="Library", user=user, imports=imports)


@router.post("/library/previews")
def library_preview_form(request: Request, _: Annotated[Principal, Depends(require_csrf)]) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        library_import = create_library_import_preview(
            session, owner=user, media_root=request.app.state.settings.media_root
        )
        library_import_id = library_import.id
        session.commit()
    return redirect(f"/library/imports/{library_import_id}")


@router.get("/library/imports/{library_import_id}", response_class=HTMLResponse)
def library_import_page(library_import_id: int, request: Request) -> HTMLResponse:
    with Session(request.app.state.engine) as session:
        user = current_user(request, session)
        if user is None:
            return redirect("/login")
        library_import = session.get(LibraryImport, library_import_id)
        if library_import is None or library_import.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Library import not found")
        rows = list(
            session.scalars(select(LibraryImportRow).where(LibraryImportRow.library_import_id == library_import.id))
        )
        return render(
            request,
            "library_import.html",
            title="Library import",
            user=user,
            library_import=library_import,
            rows=rows,
        )


@router.post("/library/imports/{library_import_id}/approve")
def approve_library_import_form(
    library_import_id: int, request: Request, _: Annotated[Principal, Depends(require_csrf)]
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        library_import = session.get(LibraryImport, library_import_id)
        if library_import is None or library_import.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Library import not found")
        approve_library_import(session, library_import, user, request.app.state.settings.media_root)
        session.commit()
    return redirect(f"/library/imports/{library_import_id}")


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    with Session(request.app.state.engine) as session:
        user = current_user(request, session)
        if user is None:
            return redirect("/login")
        batch_size = get_download_batch_size(session, request.app.state.settings.default_download_batch_size)
        return render(request, "settings.html", title="Settings", user=user, batch_size=batch_size)


@router.post("/settings")
def update_settings_form(
    request: Request,
    default_download_batch_size: Annotated[int, Form()],
    _: Annotated[Principal, Depends(require_csrf)],
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        set_download_batch_size(session, default_download_batch_size, user)
        session.commit()
    request.session["flash"] = ("success", "Settings saved.")
    return redirect("/settings")
