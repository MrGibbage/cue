from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    token_prefix: Mapped[str] = mapped_column(String(16), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    scopes_json: Mapped[str] = mapped_column(Text, default="[]")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    candidate_policy_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CollectionVersion(Base):
    __tablename__ = "collection_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    recipe_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), index=True)
    collection_version_id: Mapped[int] = mapped_column(
        ForeignKey("collection_versions.id", ondelete="RESTRICT"), index=True
    )
    adapter: Mapped[str] = mapped_column(String(64))
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    raw_document_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="previewed", index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SourceRow(Base):
    __tablename__ = "source_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("source_snapshots.id", ondelete="CASCADE"), index=True)
    source_position: Mapped[int] = mapped_column(Integer)
    supplied_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artists_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    canonical_key: Mapped[str | None] = mapped_column(String(2048), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text)


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[int] = mapped_column(primary_key=True)
    artists_json: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(1024))
    canonical_key: Mapped[str] = mapped_column(String(2048), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CollectionEntry(Base):
    __tablename__ = "collection_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_version_id: Mapped[int] = mapped_column(
        ForeignKey("collection_versions.id", ondelete="CASCADE"), index=True
    )
    recording_id: Mapped[int] = mapped_column(ForeignKey("recordings.id", ondelete="RESTRICT"), index=True)
    source_row_id: Mapped[int] = mapped_column(ForeignKey("source_rows.id", ondelete="RESTRICT"), unique=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="unresolved")


class CandidateAsset(Base):
    __tablename__ = "candidate_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    provider_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(1024))
    uploader: Mapped[str | None] = mapped_column(String(512), nullable=True)
    uploader_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    classifications_json: Mapped[str] = mapped_column(Text, default="[]")
    score: Mapped[int] = mapped_column(Integer)
    reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="candidate")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CollectionResolution(Base):
    __tablename__ = "collection_resolutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_entry_id: Mapped[int] = mapped_column(
        ForeignKey("collection_entries.id", ondelete="CASCADE"), unique=True, index=True
    )
    candidate_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="unresolved", index=True)
    selected_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    selected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PublishedAsset(Base):
    __tablename__ = "published_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_asset_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_assets.id", ondelete="RESTRICT"), unique=True, index=True, nullable=True
    )
    recording_id: Mapped[int | None] = mapped_column(
        ForeignKey("recordings.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    relative_path: Mapped[str] = mapped_column(String(2048), unique=True)
    container: Mapped[str] = mapped_column(String(16))
    byte_size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LibraryImport(Base):
    __tablename__ = "library_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    scanned_files: Mapped[int] = mapped_column(Integer, default=0)
    scanned_directories: Mapped[int] = mapped_column(Integer, default=0)
    current_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LibraryImportRow(Base):
    __tablename__ = "library_import_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_import_id: Mapped[int] = mapped_column(
        ForeignKey("library_imports.id", ondelete="CASCADE"), index=True
    )
    relative_path: Mapped[str] = mapped_column(String(2048))
    byte_size: Mapped[int] = mapped_column(Integer)
    container: Mapped[str] = mapped_column(String(16))
    artists_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    descriptor: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    canonical_key: Mapped[str | None] = mapped_column(String(2048), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("published_assets.id", ondelete="SET NULL"), nullable=True
    )


class PlaylistExport(Base):
    __tablename__ = "playlist_exports"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="previewed", index=True)
    manifest_json: Mapped[str] = mapped_column(Text)
    m3u8_relative_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    report_relative_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ApplicationSetting(Base):
    __tablename__ = "application_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    claimed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class JobAttempt(Base):
    __tablename__ = "job_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(128))
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
