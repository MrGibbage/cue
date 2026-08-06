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
from cue.library import publish_atomically, safe_filename
from cue.logging import configure_logging
from cue.models import (
    CandidateAsset,
    CollectionEntry,
    CollectionResolution,
    PlaylistExport,
    PublishedAsset,
    Recording,
    SourceSnapshot,
)
from cue.notifications import notify
from cue.providers import download_youtube, search_youtube, validate_video
from cue.publishers import write_export_artifacts
from cue.queue import claim_next_job, finish_job
from cue.services import decide_resolution, get_download_batch_size, queue_candidate_download, store_youtube_candidates

logger = logging.getLogger(__name__)


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
    if job.kind == "resolve_source_snapshot":
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
                    finish_job(session, job)
                    session.commit()
                except Exception as exc:
                    logger.exception("Job %s failed", job.id)
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
