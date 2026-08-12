from __future__ import annotations

import json
import secrets
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cue.auth import Principal, password_hash, require_csrf
from cue.discovery import apply_discovery_recipe, parse_document, parse_json_document_bytes, parse_uploaded_document
from cue.discovery_providers import fetch_billboard_hot_100, fetch_xmplaylist_recent
from cue.models import (
    AuditEvent,
    CandidateAsset,
    Collection,
    CollectionEntry,
    CollectionResolution,
    CollectionVersion,
    LibraryImport,
    LibraryImportRow,
    PlaylistExport,
    PublishedAsset,
    Recording,
    SourceRow,
    SourceSnapshot,
    User,
)
from cue.services import (
    approve_library_import,
    approve_playlist_export,
    approve_snapshot,
    assess_candidate,
    cancel_library_import_scan,
    candidate_policy,
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
LIBRARY_PAGE_SIZE = 100


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
def collection_page(collection_id: int, request: Request, draft_document: str = "") -> HTMLResponse:
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
        snapshot_provenance = {
            snapshot.id: json.loads(snapshot.raw_document_json).get("provenance")
            for snapshot in snapshots
            if snapshot.adapter != "json"
        }
        snapshot_rows = list(
            session.scalars(select(SourceRow).where(SourceRow.snapshot_id.in_([snapshot.id for snapshot in snapshots])))
        )
        snapshot_counts = {
            snapshot.id: preview_counts(row for row in snapshot_rows if row.snapshot_id == snapshot.id)
            for snapshot in snapshots
        }
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
                policy = candidate_policy(collection)
                raw_candidates = list(
                    session.scalars(
                        select(CandidateAsset)
                        .where(CandidateAsset.recording_id == recording.id)
                        .order_by(CandidateAsset.score.desc())
                    )
                )
                candidates = []
                for candidate in raw_candidates:
                    policy_score, allowed, policy_reasons = assess_candidate(candidate, policy)
                    candidates.append(
                        {
                            "candidate": candidate,
                            "policy_score": policy_score,
                            "allowed": allowed,
                            "policy_reasons": policy_reasons,
                        }
                    )
                candidates.sort(key=lambda item: (not item["allowed"], -item["policy_score"], item["candidate"].id))
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
            snapshot_counts=snapshot_counts,
            snapshot_provenance=snapshot_provenance,
            latest=latest,
            items=items,
            candidate_policy=policy if latest else candidate_policy(collection),
            draft_document=draft_document,
        )


@router.post("/collections/{collection_id}/candidate-policy")
def update_candidate_policy_form(
    collection_id: int,
    request: Request,
    channel_mode: Annotated[str, Form()],
    channel_ids: Annotated[str, Form()] = "",
    _: Annotated[Principal, Depends(require_csrf)] = None,
) -> RedirectResponse:
    if channel_mode not in {"prefer", "only", "exclude"}:
        raise HTTPException(status_code=422, detail="Invalid channel policy")
    ids = [line.strip() for line in channel_ids.splitlines() if line.strip()]
    if any(len(value) > 255 for value in ids):
        raise HTTPException(status_code=422, detail="Channel IDs must be at most 255 characters")
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        collection = session.get(Collection, collection_id)
        if collection is None or collection.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Collection not found")
        collection.candidate_policy_json = json.dumps(
            {"channel_mode": channel_mode, "channel_ids": ids}, sort_keys=True
        )
        write_audit(
            session, actor_id=user.id, action="collection.candidate_policy_updated", entity_type="collection",
            entity_id=collection.id, detail=json.loads(collection.candidate_policy_json)
        )
        session.commit()
    return redirect(f"/collections/{collection_id}")


@router.get("/snapshots/{snapshot_id}", response_class=HTMLResponse)
def snapshot_page(snapshot_id: int, request: Request) -> HTMLResponse:
    with Session(request.app.state.engine) as session:
        user = current_user(request, session)
        if user is None:
            return redirect("/login")
        snapshot = session.get(SourceSnapshot, snapshot_id)
        if snapshot is None or session.get(Collection, snapshot.collection_id).owner_id != user.id:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        rows = list(
            session.scalars(
                select(SourceRow).where(SourceRow.snapshot_id == snapshot.id).order_by(SourceRow.source_position)
            )
        )
        return render(
            request,
            "snapshot.html",
            title=f"Snapshot #{snapshot.id}",
            user=user,
            snapshot=snapshot,
            document=json.loads(snapshot.raw_document_json),
            rows=rows,
            counts=preview_counts(rows),
        )


@router.get("/snapshots/{snapshot_id}/document.json")
def download_snapshot_document(snapshot_id: int, request: Request) -> Response:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        snapshot = session.get(SourceSnapshot, snapshot_id)
        if snapshot is None or session.get(Collection, snapshot.collection_id).owner_id != user.id:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        return Response(
            content=snapshot.raw_document_json,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="cue-source-snapshot-{snapshot.id}.json"'},
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
) -> Response:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        collection = session.get(Collection, collection_id)
        if collection is None or collection.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Collection not found")
        try:
            payload = parse_json_document_bytes(document.encode("utf-8"))
            preview = parse_document(payload)
            snapshot = create_json_preview(
                session, collection=collection, owner=user, document=payload, preview=preview
            )
            session.commit()
            request.session["flash"] = ("success", preview_created_message(snapshot.id, preview.rows))
        except (ValueError, json.JSONDecodeError) as exc:
            request.session["flash"] = ("error", f"JSON was not accepted: {exc}")
            return collection_page(collection_id, request, draft_document=document)
    return redirect(f"/collections/{collection_id}")


@router.post("/collections/{collection_id}/json-upload-previews")
async def json_upload_preview_form(
    collection_id: int,
    request: Request,
    _: Annotated[Principal, Depends(require_csrf)],
    file: Annotated[UploadFile, File()],
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        collection = session.get(Collection, collection_id)
        if collection is None or collection.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Collection not found")
        try:
            if not file.filename or not file.filename.lower().endswith(".json"):
                raise ValueError("Upload a .json file")
            payload = parse_uploaded_document(await file.read())
            preview = parse_document(payload)
            snapshot = create_json_preview(
                session, collection=collection, owner=user, document=payload, preview=preview
            )
            session.commit()
            request.session["flash"] = (
                "success",
                f"{preview_created_message(snapshot.id, preview.rows)} Uploaded from {file.filename}.",
            )
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            request.session["flash"] = ("error", f"JSON was not accepted: {exc}")
    return redirect(f"/collections/{collection_id}")


@router.post("/collections/{collection_id}/billboard-hot-100-previews")
def billboard_hot_100_preview_form(
    collection_id: int,
    request: Request,
    configured_source: Annotated[str, Form()],
    chart_date: Annotated[date | None, Form()] = None,
    _: Annotated[Principal, Depends(require_csrf)] = None,
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        collection = session.get(Collection, collection_id)
        if collection is None or collection.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Collection not found")
        try:
            provider_document = fetch_billboard_hot_100(configured_source, chart_date)
            document = apply_discovery_recipe(provider_document.document, collection_recipe(session, collection.id))
            snapshot = create_json_preview(
                session,
                collection=collection,
                owner=user,
                document=document,
                preview=parse_document(document),
                adapter="billboard_hot_100",
            )
            session.commit()
            request.session["flash"] = ("success", f"Created Billboard preview #{snapshot.id}.")
        except ValueError as exc:
            record_provider_failure(session, user, "billboard_hot_100", exc)
            session.commit()
            request.session["flash"] = ("error", str(exc))
    return redirect(f"/collections/{collection_id}")


@router.post("/collections/{collection_id}/xmplaylist-previews")
def xmplaylist_preview_form(
    collection_id: int,
    request: Request,
    window_hours: Annotated[int, Form()] = 24,
    _: Annotated[Principal, Depends(require_csrf)] = None,
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        collection = session.get(Collection, collection_id)
        if collection is None or collection.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Collection not found")
        try:
            provider_document = fetch_xmplaylist_recent("altnation", window_hours)
            document = apply_discovery_recipe(provider_document.document, collection_recipe(session, collection.id))
            snapshot = create_json_preview(
                session,
                collection=collection,
                owner=user,
                document=document,
                preview=parse_document(document),
                adapter="xmplaylist_recent",
            )
            session.commit()
            request.session["flash"] = ("success", f"Created Alt Nation preview #{snapshot.id}.")
        except ValueError as exc:
            record_provider_failure(session, user, "xmplaylist_recent", exc)
            session.commit()
            request.session["flash"] = ("error", str(exc))
    return redirect(f"/collections/{collection_id}")


def collection_recipe(session: Session, collection_id: int) -> dict[str, object]:
    version = session.scalar(
        select(CollectionVersion)
        .where(CollectionVersion.collection_id == collection_id)
        .order_by(CollectionVersion.version.desc())
    )
    return json.loads(version.recipe_json) if version is not None else {}


def preview_counts(rows: Iterable[object]) -> dict[str, int]:
    states = ("accepted", "duplicate", "rejected")
    rows = list(rows)
    return {state: sum(getattr(row, "status", None) == state for row in rows) for state in states}


def preview_created_message(snapshot_id: int, rows: Iterable[object]) -> str:
    counts = preview_counts(rows)
    return (
        f"Created preview #{snapshot_id}: {counts['accepted']} accepted, "
        f"{counts['duplicate']} duplicates, {counts['rejected']} rejected."
    )


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
        source_row = session.get(SourceRow, entry.source_row_id)
        snapshot = session.get(SourceSnapshot, source_row.snapshot_id) if source_row else None
        collection = session.get(Collection, snapshot.collection_id) if snapshot else None
        if collection is None or collection.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Candidate not found")
        _, allowed, _ = assess_candidate(candidate, candidate_policy(collection))
        if not allowed:
            request.session["flash"] = ("error", "This collection's channel policy does not allow that candidate.")
            return redirect(f"/collections/{collection.id}")
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
        return redirect(f"/collections/{snapshot.collection_id}" if snapshot else "/")


@router.get("/library", response_class=HTMLResponse)
def library_page(
    request: Request, page: Annotated[int, Query(ge=1)] = 1, query: Annotated[str, Query(max_length=128)] = ""
) -> HTMLResponse:
    with Session(request.app.state.engine) as session:
        user = current_user(request, session)
        if user is None:
            return redirect("/login")
        imports = list(
            session.scalars(
                select(LibraryImport)
                .where(LibraryImport.owner_id == user.id)
                .order_by(LibraryImport.id.desc())
                .limit(100)
            )
        )
        needle = query.strip()
        filters = []
        if needle:
            pattern = f"%{needle}%"
            filters.append(
                or_(
                    PublishedAsset.relative_path.ilike(pattern),
                    Recording.title.ilike(pattern),
                    Recording.artists_json.ilike(pattern),
                )
            )
        total_assets = session.scalar(
            select(func.count())
            .select_from(PublishedAsset)
            .join(Recording, PublishedAsset.recording_id == Recording.id)
            .where(*filters)
        ) or 0
        assets = session.execute(
            select(PublishedAsset, Recording)
            .join(Recording, PublishedAsset.recording_id == Recording.id)
            .where(*filters)
            .order_by(PublishedAsset.relative_path)
            .offset((page - 1) * LIBRARY_PAGE_SIZE)
            .limit(LIBRARY_PAGE_SIZE)
        ).all()
        return render(
            request,
            "library.html",
            title="Library",
            user=user,
            imports=imports,
            assets=assets,
            total_assets=total_assets,
            page=page,
            query=needle,
            has_next=page * LIBRARY_PAGE_SIZE < total_assets,
        )


@router.post("/library/previews")
def library_preview_form(request: Request, _: Annotated[Principal, Depends(require_csrf)]) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        library_import = create_library_import_preview(
            session, owner=user
        )
        library_import_id = library_import.id
        session.commit()
    return redirect(f"/library/imports/{library_import_id}")


@router.get("/library/imports/{library_import_id}", response_class=HTMLResponse)
def library_import_page(
    library_import_id: int, request: Request, page: Annotated[int, Query(ge=1)] = 1
) -> HTMLResponse:
    with Session(request.app.state.engine) as session:
        user = current_user(request, session)
        if user is None:
            return redirect("/login")
        library_import = session.get(LibraryImport, library_import_id)
        if library_import is None or library_import.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Library import not found")
        total_rows = session.scalar(
            select(func.count())
            .select_from(LibraryImportRow)
            .where(LibraryImportRow.library_import_id == library_import.id)
        ) or 0
        rows = list(
            session.scalars(
                select(LibraryImportRow)
                .where(LibraryImportRow.library_import_id == library_import.id)
                .order_by(LibraryImportRow.id)
                .offset((page - 1) * LIBRARY_PAGE_SIZE)
                .limit(LIBRARY_PAGE_SIZE)
            )
        )
        return render(
            request,
            "library_import.html",
            title="Library import",
            user=user,
            library_import=library_import,
            rows=rows,
            total_rows=total_rows,
            page=page,
            has_next=page * LIBRARY_PAGE_SIZE < total_rows,
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
        try:
            approve_library_import(session, library_import, user, request.app.state.settings.media_root)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        session.commit()
    return redirect(f"/library/imports/{library_import_id}")


@router.post("/library/imports/{library_import_id}/cancel")
def cancel_library_import_form(
    library_import_id: int, request: Request, _: Annotated[Principal, Depends(require_csrf)]
) -> RedirectResponse:
    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        library_import = session.get(LibraryImport, library_import_id)
        if library_import is None or library_import.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Library import not found")
        try:
            cancel_library_import_scan(session, library_import, user)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
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


@router.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request) -> HTMLResponse:
    from cue.models import Job
    with Session(request.app.state.engine) as session:
        user = current_user(request, session)
        if user is None:
            return redirect("/login")
        jobs = list(session.scalars(select(Job).where(Job.owner_id == user.id).order_by(Job.id.desc()).limit(100)))
        return render(request, "jobs.html", title="Jobs", user=user, jobs=jobs)


@router.get("/diagnostics", response_class=HTMLResponse)
def diagnostics_page(request: Request) -> HTMLResponse:
    from cue.models import Job

    with Session(request.app.state.engine) as session:
        user = current_user(request, session)
        if user is None:
            return redirect("/login")
        backup_files = sorted(request.app.state.settings.backup_root.glob("cue-????-??-??.sqlite3"))
        provider_failures = list(
            session.scalars(
                select(AuditEvent)
                .where(AuditEvent.actor_id == user.id, AuditEvent.action == "provider.fetch_failed")
                .order_by(AuditEvent.id.desc())
                .limit(10)
            )
        )
        return render(
            request,
            "diagnostics.html",
            title="Diagnostics",
            user=user,
            latest_backup=backup_files[-1].name if backup_files else None,
            failed=len(list(session.scalars(select(Job.id).where(Job.owner_id == user.id, Job.status == "failed")))),
            queued=len(list(session.scalars(select(Job.id).where(Job.owner_id == user.id, Job.status == "queued")))),
            review=len(
                list(session.scalars(select(CollectionResolution.id).where(CollectionResolution.status == "review")))
            ),
            provider_failures=[
                {"adapter": event.entity_id, **json.loads(event.detail_json)} for event in provider_failures
            ],
        )


def record_provider_failure(session: Session, user: User, adapter: str, error: ValueError) -> None:
    write_audit(
        session,
        actor_id=user.id,
        action="provider.fetch_failed",
        entity_type="provider",
        entity_id=adapter,
        detail={"error": str(error)},
    )


@router.post("/jobs/{job_id}/retry")
def retry_job_form(job_id: int, request: Request, _: Annotated[Principal, Depends(require_csrf)]) -> RedirectResponse:
    from cue.models import Job

    with Session(request.app.state.engine) as session:
        user = require_web_user(request, session)
        job = session.get(Job, job_id)
        if job is None or job.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status != "failed":
            raise HTTPException(status_code=409, detail="Only failed jobs may be retried")
        job.status, job.claimed_at, job.claimed_by = "queued", None, None
        write_audit(session, actor_id=user.id, action="job.retried", entity_type="job", entity_id=job.id)
        session.commit()
    return redirect("/jobs")


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
