from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from cue.auth import password_hash
from cue.discovery import PreviewDocument
from cue.models import (
    ApplicationSetting,
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
    PublishedAsset,
    Recording,
    Role,
    SourceRow,
    SourceSnapshot,
    User,
    UserRole,
)
from cue.providers import ProviderCandidate
from cue.scoring import score_candidate


def store_youtube_candidates(
    session: Session, recording: Recording, candidates: list[ProviderCandidate]
) -> list[CandidateAsset]:
    stored: list[CandidateAsset] = []
    artists = json.loads(recording.artists_json)
    for candidate in candidates:
        score = score_candidate(artists, recording.title, candidate.title, candidate.uploader)
        existing = session.scalar(
            select(CandidateAsset).where(
                CandidateAsset.provider == "youtube", CandidateAsset.provider_id == candidate.provider_id
            )
        )
        if existing is None:
            existing = CandidateAsset(
                recording_id=recording.id,
                provider="youtube",
                provider_id=candidate.provider_id,
                url=candidate.url,
                title=candidate.title,
                uploader=candidate.uploader,
                duration_seconds=candidate.duration_seconds,
                classifications_json=json.dumps(score.classifications),
                score=score.score,
                reasons_json=json.dumps(score.reasons),
            )
            session.add(existing)
        else:
            existing.title = candidate.title
            existing.uploader = candidate.uploader
            existing.duration_seconds = candidate.duration_seconds
            existing.classifications_json = json.dumps(score.classifications)
            existing.score = score.score
            existing.reasons_json = json.dumps(score.reasons)
        stored.append(existing)
    session.flush()
    return stored


def rescore_recording_candidates(session: Session, recording: Recording) -> None:
    """Refresh persisted search evidence when ranking rules improve."""
    artists = json.loads(recording.artists_json)
    for candidate in session.scalars(select(CandidateAsset).where(CandidateAsset.recording_id == recording.id)):
        score = score_candidate(artists, recording.title, candidate.title, candidate.uploader)
        candidate.classifications_json = json.dumps(score.classifications)
        candidate.score = score.score
        candidate.reasons_json = json.dumps(score.reasons)


def decide_resolution(
    session: Session, entry: CollectionEntry, candidates: list[CandidateAsset]
) -> CollectionResolution:
    """Apply the strict default policy without downloading anything."""
    resolution = session.scalar(
        select(CollectionResolution).where(CollectionResolution.collection_entry_id == entry.id)
    )
    if resolution is None:
        resolution = CollectionResolution(collection_entry_id=entry.id)
        session.add(resolution)
    clear = [
        candidate
        for candidate in candidates
        if "official_music_video" in json.loads(candidate.classifications_json) and candidate.score >= 100
    ]
    if len(clear) == 1:
        resolution.candidate_asset_id = clear[0].id
        resolution.status = "auto_selected"
        clear[0].status = "selected"
    elif candidates:
        resolution.candidate_asset_id = None
        resolution.status = "review"
    else:
        resolution.candidate_asset_id = None
        resolution.status = "unresolved"
    session.flush()
    return resolution


def queue_candidate_download(session: Session, *, owner: User, resolution: CollectionResolution) -> Job:
    if resolution.candidate_asset_id is None:
        raise ValueError("A candidate must be selected before it can be downloaded")
    payload = json.dumps(
        {"candidate_id": resolution.candidate_asset_id, "resolution_id": resolution.id}, sort_keys=True
    )
    existing = session.scalar(
        select(Job).where(
            Job.kind == "download_candidate",
            Job.status.in_(("queued", "running", "succeeded")),
            Job.payload_json == payload,
        )
    )
    if existing is not None:
        return existing
    job = Job(owner_id=owner.id, kind="download_candidate", payload_json=payload)
    session.add(job)
    session.flush()
    return job


def write_audit(
    session: Session,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | int,
    detail: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            detail_json=json.dumps(detail or {}, sort_keys=True),
        )
    )


def create_admin(session: Session, username: str, password: str) -> User:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("Username must not be empty")
    if session.scalar(select(User).where(User.username == normalized_username)):
        raise ValueError("Username already exists")
    role = session.scalar(select(Role).where(Role.name == "administrator"))
    if role is None:
        role = Role(name="administrator")
        session.add(role)
        session.flush()
    user = User(username=normalized_username, password_hash=password_hash.hash(password))
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    write_audit(
        session,
        actor_id=user.id,
        action="user.bootstrap_created",
        entity_type="user",
        entity_id=user.id,
        detail={"username": user.username},
    )
    return user


def bootstrap_admin(session: Session, username: str | None, password: str | None) -> None:
    if not username or not password or session.scalar(select(User.id).limit(1)) is not None:
        return
    create_admin(session, username, password)
    session.commit()


def create_collection(session: Session, owner: User, name: str, recipe: dict[str, object]) -> Collection:
    collection = Collection(owner_id=owner.id, name=name.strip())
    session.add(collection)
    session.flush()
    session.add(
        CollectionVersion(
            collection_id=collection.id,
            version=1,
            recipe_json=json.dumps(recipe, sort_keys=True),
            created_by_id=owner.id,
        )
    )
    write_audit(
        session,
        actor_id=owner.id,
        action="collection.created",
        entity_type="collection",
        entity_id=collection.id,
        detail={"name": collection.name},
    )
    return collection


def revoke_token(session: Session, token_id: int, actor: User) -> bool:
    from cue.models import ApiToken

    token = session.get(ApiToken, token_id)
    if token is None or token.user_id != actor.id or token.revoked_at is not None:
        return False
    token.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    write_audit(
        session,
        actor_id=actor.id,
        action="token.revoked",
        entity_type="api_token",
        entity_id=token.id,
    )
    return True


def latest_collection_version(session: Session, collection_id: int) -> CollectionVersion:
    version = session.scalar(
        select(CollectionVersion)
        .where(CollectionVersion.collection_id == collection_id)
        .order_by(CollectionVersion.version.desc())
    )
    if version is None:
        raise ValueError("Collection has no version")
    return version


def create_json_preview(
    session: Session,
    *,
    collection: Collection,
    owner: User,
    document: dict[str, object] | list[object],
    preview: PreviewDocument,
    adapter: str = "json",
) -> SourceSnapshot:
    snapshot = SourceSnapshot(
        collection_id=collection.id,
        collection_version_id=latest_collection_version(session, collection.id).id,
        adapter=adapter,
        source_name=preview.source_name,
        source_url=preview.source_url,
        raw_document_json=json.dumps(document, sort_keys=True),
        created_by_id=owner.id,
    )
    session.add(snapshot)
    session.flush()
    for row in preview.rows:
        session.add(
            SourceRow(
                snapshot_id=snapshot.id,
                source_position=row.position,
                supplied_rank=row.supplied_rank,
                artists_json=json.dumps(row.artists) if row.artists else None,
                title=row.title,
                canonical_key=row.canonical_key,
                status=row.status,
                error=row.error,
                raw_json=json.dumps(row.raw, sort_keys=True),
            )
        )
    write_audit(
        session,
        actor_id=owner.id,
        action="source_snapshot.previewed",
        entity_type="source_snapshot",
        entity_id=snapshot.id,
        detail={"adapter": adapter, "row_count": len(preview.rows)},
    )
    return snapshot


def approve_snapshot(session: Session, snapshot: SourceSnapshot, owner: User) -> Job:
    if snapshot.status != "previewed":
        raise ValueError("Snapshot has already been approved")
    rows = list(
        session.scalars(
            select(SourceRow)
            .where(SourceRow.snapshot_id == snapshot.id, SourceRow.status == "accepted")
            .order_by(SourceRow.supplied_rank.is_(None), SourceRow.supplied_rank, SourceRow.source_position)
        )
    )
    if not rows:
        raise ValueError("A preview needs at least one accepted song before it can be approved")
    existing_entry = session.scalar(
        select(CollectionEntry.id)
        .where(CollectionEntry.collection_version_id == snapshot.collection_version_id)
        .limit(1)
    )
    if existing_entry is not None:
        previous_version = session.get(CollectionVersion, snapshot.collection_version_id)
        if previous_version is None:
            raise ValueError("Snapshot collection version no longer exists")
        latest_version = latest_collection_version(session, snapshot.collection_id)
        replacement_version = CollectionVersion(
            collection_id=snapshot.collection_id,
            version=latest_version.version + 1,
            recipe_json=previous_version.recipe_json,
            created_by_id=owner.id,
        )
        session.add(replacement_version)
        session.flush()
        snapshot.collection_version_id = replacement_version.id
    for ordinal, row in enumerate(rows, start=1):
        recording = session.scalar(select(Recording).where(Recording.canonical_key == row.canonical_key))
        if recording is None:
            recording = Recording(
                artists_json=row.artists_json or "[]",
                title=row.title or "",
                canonical_key=row.canonical_key or "",
            )
            session.add(recording)
            session.flush()
        session.add(
            CollectionEntry(
                collection_version_id=snapshot.collection_version_id,
                recording_id=recording.id,
                source_row_id=row.id,
                ordinal=ordinal,
            )
        )
    snapshot.status = "approved"
    snapshot.approved_at = datetime.now(UTC).replace(tzinfo=None)
    snapshot.approved_by_id = owner.id
    job = Job(
        owner_id=owner.id,
        kind="resolve_source_snapshot",
        payload_json=json.dumps({"snapshot_id": snapshot.id}),
    )
    session.add(job)
    session.flush()
    write_audit(
        session,
        actor_id=owner.id,
        action="source_snapshot.approved",
        entity_type="source_snapshot",
        entity_id=snapshot.id,
        detail={"accepted_rows": len(rows), "job_id": job.id, "collection_version_id": snapshot.collection_version_id},
    )
    return job


def create_library_import_preview(
    session: Session, *, owner: User, source_name: str | None = None
) -> LibraryImport:
    """Create a durable, read-only library scan request."""
    library_import = LibraryImport(
        owner_id=owner.id, source_name=source_name.strip() if source_name else None, status="queued"
    )
    session.add(library_import)
    session.flush()
    job = Job(
        owner_id=owner.id,
        kind="scan_library_import",
        payload_json=json.dumps({"library_import_id": library_import.id}),
        max_attempts=1,
    )
    session.add(job)
    session.flush()
    write_audit(
        session,
        actor_id=owner.id,
        action="library_import.queued",
        entity_type="library_import",
        entity_id=library_import.id,
        detail={"source_name": library_import.source_name, "job_id": job.id},
    )
    return library_import


def cancel_library_import_scan(session: Session, library_import: LibraryImport, owner: User) -> None:
    if library_import.status not in {"queued", "scanning"}:
        raise ValueError("Only queued or scanning library imports can be cancelled")
    library_import.status = "cancelled"
    library_import.cancelled_at = datetime.now(UTC).replace(tzinfo=None)
    library_import.current_path = None
    job = session.scalar(
        select(Job)
        .where(
            Job.kind == "scan_library_import",
            Job.payload_json.contains(f'"library_import_id": {library_import.id}'),
        )
        .order_by(Job.id.desc())
        .limit(1)
    )
    if job is not None and job.status in {"queued", "running"}:
        if job.status == "running":
            attempt = session.scalar(
                select(JobAttempt).where(
                    JobAttempt.job_id == job.id, JobAttempt.attempt_number == job.attempt_count
                )
            )
            if attempt is not None:
                attempt.status = "cancelled"
                attempt.finished_at = datetime.now(UTC).replace(tzinfo=None)
        job.status, job.claimed_at, job.claimed_by = "cancelled", None, None
    write_audit(
        session,
        actor_id=owner.id,
        action="library_import.cancelled",
        entity_type="library_import",
        entity_id=library_import.id,
    )


def approve_library_import(session: Session, library_import: LibraryImport, owner: User, media_root: Path) -> int:
    if library_import.status != "previewed":
        raise ValueError("Library import scan must complete successfully before approval")
    root = media_root.resolve()
    rows = list(
        session.scalars(
            select(LibraryImportRow)
            .where(LibraryImportRow.library_import_id == library_import.id, LibraryImportRow.status == "accepted")
            .order_by(LibraryImportRow.id)
        )
    )
    imported = 0
    for row in rows:
        path = (root / row.relative_path).resolve()
        if root not in path.parents or not path.is_file():
            row.status = "review"
            row.error = "File no longer exists beneath the configured media root"
            continue
        if path.stat().st_size != row.byte_size:
            row.status = "review"
            row.error = "File changed after preview; create a new preview before importing"
            continue
        if session.scalar(select(PublishedAsset).where(PublishedAsset.relative_path == row.relative_path)):
            row.status = "already_imported"
            row.error = "This path is already managed by Cue"
            continue
        recording = session.scalar(select(Recording).where(Recording.canonical_key == row.canonical_key))
        if recording is None:
            recording = Recording(
                artists_json=row.artists_json or "[]", title=row.title or "", canonical_key=row.canonical_key or ""
            )
            session.add(recording)
            session.flush()
        asset = PublishedAsset(
            recording_id=recording.id,
            relative_path=row.relative_path,
            container=row.container,
            byte_size=row.byte_size,
        )
        session.add(asset)
        session.flush()
        row.published_asset_id = asset.id
        row.status = "imported"
        row.error = None
        imported += 1
    library_import.status = "approved"
    library_import.approved_at = datetime.now(UTC).replace(tzinfo=None)
    library_import.approved_by_id = owner.id
    write_audit(
        session,
        actor_id=owner.id,
        action="library_import.approved",
        entity_type="library_import",
        entity_id=library_import.id,
        detail={"imported_rows": imported},
    )
    return imported


def create_playlist_export_preview(
    session: Session,
    *,
    collection: Collection,
    owner: User,
    name: str | None,
    media_root: Path,
    m3u_path_prefix: str | None,
) -> PlaylistExport:
    snapshot = session.scalar(
        select(SourceSnapshot)
        .where(SourceSnapshot.collection_id == collection.id, SourceSnapshot.status == "approved")
        .order_by(SourceSnapshot.id.desc())
    )
    if snapshot is None:
        raise ValueError("Collection has no approved source snapshot to export")
    rows = session.execute(
        select(CollectionEntry, Recording, CollectionResolution)
        .join(Recording, CollectionEntry.recording_id == Recording.id)
        .join(SourceRow, CollectionEntry.source_row_id == SourceRow.id)
        .outerjoin(CollectionResolution, CollectionResolution.collection_entry_id == CollectionEntry.id)
        .where(SourceRow.snapshot_id == snapshot.id)
        .order_by(CollectionEntry.ordinal)
    ).all()
    resolved: list[dict[str, object]] = []
    missing: list[dict[str, object]] = []
    root = media_root.resolve()
    for entry, recording, resolution in rows:
        asset = session.scalar(
            select(PublishedAsset).where(PublishedAsset.recording_id == recording.id).order_by(PublishedAsset.id)
        )
        display_name = f"{' & '.join(json.loads(recording.artists_json))} - {recording.title}"
        if resolution is None or resolution.status != "published":
            reason = resolution.status if resolution else "unresolved"
            missing.append(_missing_export_item(entry, recording, display_name, reason))
        elif asset is None:
            missing.append(_missing_export_item(entry, recording, display_name, "asset_not_recorded"))
        elif not (root / asset.relative_path).is_file():
            missing.append(_missing_export_item(entry, recording, display_name, "file_missing"))
        else:
            resolved.append(
                {
                    "ordinal": entry.ordinal,
                    "recording_id": recording.id,
                    "display_name": display_name,
                    "relative_path": asset.relative_path,
                    "playlist_path": _playlist_path(asset.relative_path, m3u_path_prefix),
                }
            )
    manifest = {
        "collection_id": collection.id,
        "source_snapshot_id": snapshot.id,
        "resolved": resolved,
        "missing": missing,
    }
    playlist_export = PlaylistExport(
        owner_id=owner.id,
        collection_id=collection.id,
        name=(name or collection.name).strip(),
        manifest_json=json.dumps(manifest, sort_keys=True),
    )
    session.add(playlist_export)
    session.flush()
    write_audit(
        session,
        actor_id=owner.id,
        action="playlist_export.previewed",
        entity_type="playlist_export",
        entity_id=playlist_export.id,
        detail={"resolved": len(resolved), "missing": len(missing)},
    )
    return playlist_export


def approve_playlist_export(session: Session, playlist_export: PlaylistExport, owner: User) -> Job:
    if playlist_export.status != "previewed":
        raise ValueError("Playlist export has already been approved")
    playlist_export.status = "approved"
    playlist_export.approved_at = datetime.now(UTC).replace(tzinfo=None)
    playlist_export.approved_by_id = owner.id
    job = Job(owner_id=owner.id, kind="publish_m3u_export", payload_json=json.dumps({"export_id": playlist_export.id}))
    session.add(job)
    session.flush()
    write_audit(
        session,
        actor_id=owner.id,
        action="playlist_export.approved",
        entity_type="playlist_export",
        entity_id=playlist_export.id,
        detail={"job_id": job.id},
    )
    return job


def _missing_export_item(
    entry: CollectionEntry, recording: Recording, display_name: str, reason: str
) -> dict[str, object]:
    return {"ordinal": entry.ordinal, "recording_id": recording.id, "display_name": display_name, "reason": reason}


def _playlist_path(relative_path: str, prefix: str | None) -> str:
    return f"{prefix.rstrip('/')}/{relative_path}" if prefix else relative_path


def get_download_batch_size(session: Session, default: int) -> int:
    setting = session.get(ApplicationSetting, "default_download_batch_size")
    if setting is None:
        return default
    try:
        value = int(setting.value)
    except ValueError:
        return default
    return value if value >= 1 else default


def set_download_batch_size(session: Session, value: int, actor: User) -> None:
    if value < 1:
        raise ValueError("Download batch size must be at least 1")
    setting = session.get(ApplicationSetting, "default_download_batch_size")
    if setting is None:
        setting = ApplicationSetting(key="default_download_batch_size", value=str(value))
        session.add(setting)
    else:
        setting.value = str(value)
    write_audit(
        session,
        actor_id=actor.id,
        action="settings.download_batch_size_updated",
        entity_type="application_setting",
        entity_id=setting.key,
        detail={"value": value},
    )
