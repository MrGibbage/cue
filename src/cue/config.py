from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, HttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, env_prefix="CUE_", extra="ignore")

    database_url: str = "sqlite:////data/cue.sqlite3"
    media_root: Path = Path("/media")
    export_root: Path = Path("/data/exports")
    m3u_path_prefix: str | None = None
    staging_root: Path | None = None
    download_workspace: Path | None = None
    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1, le=65535)
    log_level: str = "INFO"
    default_download_batch_size: int = Field(default=25, ge=1)
    apprise_url: HttpUrl | None = None
    session_secret: str = Field(min_length=32)
    bootstrap_admin_username: str | None = None
    bootstrap_admin_password: str | None = None

    @model_validator(mode="after")
    def validate_paths(self) -> Settings:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("CUE_DATABASE_URL must be a SQLite URL for the MVP")
        if self.staging_root is not None:
            try:
                self.staging_root.relative_to(self.media_root)
            except ValueError as exc:
                raise ValueError("CUE_STAGING_ROOT must be beneath CUE_MEDIA_ROOT") from exc
        if bool(self.bootstrap_admin_username) != bool(self.bootstrap_admin_password):
            raise ValueError("CUE_BOOTSTRAP_ADMIN_USERNAME and CUE_BOOTSTRAP_ADMIN_PASSWORD must be set together")
        return self

    @property
    def database_path(self) -> Path:
        return Path(self.database_url.removeprefix("sqlite:///"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
