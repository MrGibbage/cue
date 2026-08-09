from __future__ import annotations

import json
import logging
import shutil
import signal
import socket
from pathlib import Path
from threading import Event

from sqlalchemy import select
from sqlalchemy.orm import Session

from cue.backups import create_daily_backup
from cue.config import Settings, get_settings
from cue.db import create_db_engine, run_migrations
from cue.library import publish_atomically, safe_filename, scan_library
from cue.logging import configure_logging
from cue.models import (
    CandidateAsset,
    CollectionEntry,
    CollectionResolution,
    LibraryImport,
    LibraryImportRow,
    PlaylistExport,
    PublishedAsset,
    Recording,
    SourceSnapshot,
)
from cue.notifications import notify
from cue.providers import download_youtube, search_youtube, validate_video
from cue.publishers import write_export_artifacts
from cue.queue import claim_next_job, finish_job
from cue.services import (
    decide_resolution,
    get_download_batch_size,
    queue_candidate_download,
    store_youtube_candidates,
    write_audit,
)

logger = logging.getLogger(__name__)


def scan_library_import(session: Session, job_id: int, library_import_id: int, settings: Settings) -> None:
    """Persist a read-only scan in bounded transactions so long scans survive restarts."""
    library_import = session.get(LibraryImport, library_import_id)
    if library_import is None:
        raise RuntimeError("Library import not found")
    if library_import.status == "cancelled":
        return
    if library_import.status not in {"queued", "scanning"}:
        raise RuntimeError("Library import is no longer awaiting a scan")
    root = settings.media_root.resolve()
    library_import.status = "scanning"
    library_import.error = None
    session.commit()

    managed_paths = set(session.scalars(select(PublishedAsset.relative_path)))
    existing_paths = set(
        session.scalars(
            select(LibraryImportRow.relative_path).where(LibraryImportRow.library_import_id == library_import_id)
        )
    )
    seen_keys = set(
        session.scalars(
            select(LibraryImportRow.canonical_key).where(
                LibraryImportRow.library_import_id == library_import_id, LibraryImportRow.status == "accepted"
            )
        )
    )
    batch: list[LibraryImportRow] = []
    scanned_files = 0
    scanned_directories = 0
    current_path: str | None = None

    def flush_batch() -> bool:
        nonlocal batch
        session.refresh(library_import)
        if library_import.status == "cancelled":
            session.commit()
            return False
        session.add_all(batch)
        library_import.scanned_files = scanned_files
        library_import.scanned_directories = scanned_directories
        library_import.current_path = current_path
        session.commit()
        batch = []
        return True

    for path, parsed, directories in scan_library(root):
        scanned_files += 1
        scanned_directories = directories
        relative_path = path.relative_to(root).as_posix()
        current_path = relative_path
        if relative_path in existing_paths:
            continue
        try:
            byte_size = path.stat().st_size
        except OSError:
            continue
        row_status = "accepted"
        error = parsed.error
        if relative_path in managed_paths:
            row_status = "already_imported"
            error = "This path is already managed by Cue"
        elif error:
            row_status = "review"
        elif parsed.canonical_key in seen_keys:
            row_status = "review"
            error = "Another file in this preview has the same parsed recording; review alternate versions manually"
        else:
            seen_keys.add(parsed.canonical_key)
        batch.append(
            LibraryImportRow(
                library_import_id=library_import_id,
                relative_path=relative_path,
                byte_size=byte_size,
                container=path.suffix.removeprefix(".").lower(),
                artists_json=json.dumps(parsed.artists) if parsed.artists else None,
                title=parsed.title,
                descriptor=parsed.descriptor,
                year=parsed.year,
                canonical_key=parsed.canonical_key,
                status=row_status,
                error=error,
            )
        )
        if scanned_files % settings.library_scan_batch_size == 0 and not flush_batch():
            return
    if batch and not flush_batch():
        return
    session.refresh(library_import)
    if library_import.status == "cancelled":
        session.commit()
        return
    library_import.scanned_files = scanned_files
    library_import.scanned_directories = scanned_directories
    library_import.current_path = None
    library_import.status = "previewed"
    from datetime import UTC, datetime

    library_import.completed_at = datetime.now(UTC).replace(tzinfo=None)
    write_audit(
        session,
        actor_id=library_import.owner_id,
        action="library_import.previewed",
        entity_type="library_import",
        entity_id=library_import.id,
        detail={"job_id": job_id, "scanned_files": scanned_files, "scanned_directories": scanned_directories},
    )
    session.commit()


def download_candidate(session: Session, candidate_id: int, resolution_id: int, settings: Settings) -> None:
    candidate = session.get(CandidateAsset, candidate_id)
    resolution = session.get(CollectionResolution, resolution_id)
    if candidate is None or resolution is None or resolution.candidate_asset_id != candidate.id:
        raise RuntimeError("Candidate selection no longer exists")
    if session.scalar(select(PublishedAsset).where(PublishedAsset.candidate_asset_id == candidate.id)):
        return
    entry = session.get(CollectionEntry, resolution.collection_entry_id)
    recording = session.get(Recording, entry.recording_id) if entry else None
    if recording is None:
        raise RuntimeError("Recording not found")
    stage_root = settings.download_workspace or settings.staging_root or settings.media_root / ".cue-staging"
    stage_dir = Path(stage_root) / f"candidate-{candidate.id}"
    stage_dir.mkdir(parents=True, exist_ok=True)
    try:
        source = download_youtube(candidate.url, stage_dir / "download.%(ext)s")
        validate_video(source)
        filename = safe_filename(recording, candidate, source.suffix)
        destination = publish_atomically(source, settings.media_root, filename)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
    session.add(
        PublishedAsset(
            candidate_asset_id=candidate.id,
            recording_id=recording.id,
            relative_path=str(destination.relative_to(settings.media_root)),
            container=destination.suffix.removeprefix(".").lower(),
            byte_size=destination.stat().st_size,
        )
    )
    candidate.status = "published"
    resolution.status = "published"
    entry.status = "resolved"


def process_job(session: Session, job_id: int, settings: Settings) -> None:
    from cue.models import Job, User

    job = session.get(Job, job_id)
    if job is None:
        raise RuntimeError("Job not found")
    payload = json.loads(job.payload_json)
    if job.kind == "scan_library_import":
        library_import_id = payload.get("library_import_id")
        if not isinstance(library_import_id, int):
            raise RuntimeError("Invalid library import scan job payload")
        scan_library_import(session, job.id, library_import_id, settings)
    elif job.kind == "resolve_source_snapshot":
        snapshot_id = payload.get("snapshot_id")
        if not isinstance(snapshot_id, int):
            raise RuntimeError("Invalid snapshot job payload")
        snapshot = session.get(SourceSnapshot, snapshot_id)
        if snapshot is None:
            raise RuntimeError("Source snapshot not found")
        owner = session.get(User, job.owner_id)
        if owner is None:
            raise RuntimeError("Job owner not found")
        entries = list(
            session.scalars(
                select(CollectionEntry).where(CollectionEntry.collection_version_id == snapshot.collection_version_id)
            )
        )
        queued_downloads = 0
        batch_size = get_download_batch_size(session, settings.default_download_batch_size)
        review_count = 0
        for entry in entries:
            recording = session.get(Recording, entry.recording_id)
            if recording is None:
                raise RuntimeError(f"Recording {entry.recording_id} not found")
            existing_asset = session.scalar(
                select(PublishedAsset).where(PublishedAsset.recording_id == recording.id).limit(1)
            )
            if existing_asset is not None:
                resolution = decide_resolution(session, entry, [])
                resolution.status = "published"
                entry.status = "resolved"
                continue
            candidates = store_youtube_candidates(
                session, recording, search_youtube(json.loads(recording.artists_json), recording.title)
            )
            resolution = decide_resolution(session, entry, candidates)
            if resolution.status == "review":
                review_count += 1
            if resolution.status == "auto_selected":
                if queued_downloads < batch_size:
                    queue_candidate_download(session, owner=owner, resolution=resolution)
                    queued_downloads += 1
                else:
                    resolution.status = "review"
                    resolution.candidate_asset_id = None
                    review_count += 1
        if review_count:
            notify(
                settings,
                "Cue review needed",
                f"{review_count} item(s) in source snapshot #{snapshot.id} need a video decision.",
                "warning",
            )
    elif job.kind == "download_candidate":
        candidate_id, resolution_id = payload.get("candidate_id"), payload.get("resolution_id")
        if not isinstance(candidate_id, int) or not isinstance(resolution_id, int):
            raise RuntimeError("Invalid download job payload")
        download_candidate(session, candidate_id, resolution_id, settings)
    elif job.kind == "publish_m3u_export":
        export_id = payload.get("export_id")
        if not isinstance(export_id, int):
            raise RuntimeError("Invalid playlist export job payload")
        playlist_export = session.get(PlaylistExport, export_id)
        if playlist_export is None or playlist_export.status != "approved":
            raise RuntimeError("Playlist export is no longer approved")
        m3u8_path, report_path, digest = write_export_artifacts(
            settings.export_root, playlist_export.name, playlist_export.id, json.loads(playlist_export.manifest_json)
        )
        playlist_export.m3u8_relative_path = m3u8_path
        playlist_export.report_relative_path = report_path
        playlist_export.digest = digest
        playlist_export.status = "published"
    else:
        raise RuntimeError(f"Unsupported job kind: {job.kind}")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    run_migrations(settings)
    engine = create_db_engine(settings)
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    worker_id = socket.gethostname()
    logger.info("Cue worker started")
    while not stop.is_set():
        try:
            create_daily_backup(settings)
        except Exception:
            logger.exception("Daily SQLite backup failed")
        with Session(engine) as session:
            job = claim_next_job(session, worker_id)
            if job is None:
                session.rollback()
            else:
                try:
                    process_job(session, job.id, settings)
                    session.refresh(job)
                    if job.status != "cancelled":
                        finish_job(session, job)
                    session.commit()
                except Exception as exc:
                    logger.exception("Job %s failed", job.id)
                    if job.kind == "scan_library_import":
                        payload = json.loads(job.payload_json)
                        library_import_id = payload.get("library_import_id")
                        if isinstance(library_import_id, int):
                            library_import = session.get(LibraryImport, library_import_id)
                            if library_import is not None and library_import.status != "cancelled":
                                from datetime import UTC, datetime

                                library_import.status = "failed"
                                library_import.error = str(exc)
                                library_import.current_path = None
                                library_import.completed_at = datetime.now(UTC).replace(tzinfo=None)
                                write_audit(
                                    session,
                                    actor_id=library_import.owner_id,
                                    action="library_import.failed",
                                    entity_type="library_import",
                                    entity_id=library_import.id,
                                    detail={"job_id": job.id, "error": str(exc)},
                                )
                    finish_job(session, job, error=str(exc))
                    session.commit()
                    if job.status == "failed":
                        notify(
                            settings,
                            "Cue job failed",
                            f"Job #{job.id} ({job.kind}) failed: {job.last_error}",
                            "failure",
                        )
        stop.wait(2)
    engine.dispose()
    logger.info("Cue worker stopped")
