"""Application settings.

Loaded from environment variables (and optional `.env`) via pydantic-settings.
All nested fields use ``__`` as delimiter, e.g. ``DB__CONNECTION_STRING``.

The settings are intentionally engine-agnostic: switching between local
PostgreSQL+PostGIS, Neon, a filesystem object store, or any S3-compatible
endpoint (MinIO, Aruba Cloud Object Storage, R2, B2) requires *only*
environment changes, never code changes.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ObjectStoreBackend(StrEnum):
    FILESYSTEM = "filesystem"
    S3 = "s3"


class SchedulerBackend(StrEnum):
    PG_CRON = "pg_cron"
    APSCHEDULER = "apscheduler"


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    FOUNDRY = "foundry"
    OLLAMA = "ollama"


class DBSettings(BaseSettings):
    """PostgreSQL / PostGIS connection settings."""

    model_config = SettingsConfigDict(extra="ignore")

    connection_string: str = Field(
        default="postgresql://limen:limen@localhost:5432/limen",
        description="PostgreSQL DSN. Use ?sslmode=require for Neon.",
    )
    pool_min_size: int = Field(default=2, ge=1, le=100)
    pool_max_size: int = Field(default=20, ge=1, le=200)
    statement_cache_size: int = Field(default=1024, ge=0)
    command_timeout_seconds: float = Field(default=30.0, gt=0)

    @model_validator(mode="after")
    def _validate_pool(self) -> DBSettings:
        if self.pool_max_size < self.pool_min_size:
            raise ValueError("DB__POOL_MAX_SIZE must be >= DB__POOL_MIN_SIZE")
        return self


class ObjectStoreSettings(BaseSettings):
    """Object-storage settings (backend-agnostic).

    The S3 fields target any S3-compatible endpoint via ``endpoint_url`` —
    MinIO, Aruba Cloud Object Storage, R2, B2 — not just AWS S3.
    """

    model_config = SettingsConfigDict(extra="ignore")

    backend: ObjectStoreBackend = ObjectStoreBackend.FILESYSTEM
    root: Path = Path("./object_store_root")

    # S3-compatible
    bucket: str | None = None
    prefix: str = ""
    region: str | None = None
    endpoint_url: str | None = None
    access_key_id: SecretStr | None = None
    secret_access_key: SecretStr | None = None


class LLMModels(BaseSettings):
    """Per-role model mapping. Populated lazily from env (``LLM__MODELS__*``).

    The defaults below assume Anthropic Claude is the primary provider. The
    per-provider concrete factories translate role names to provider-specific
    model ids when a different provider is selected (e.g. Ollama uses
    ``qwen2.5:32b`` regardless of role unless overridden).
    """

    model_config = SettingsConfigDict(extra="allow")

    orchestrator: str = "claude-opus-4-7"
    scorer: str = "claude-sonnet-4-6"
    summarizer: str = "claude-haiku-4-5"
    risk_analyst: str = "claude-haiku-4-5"
    briefing: str = "claude-sonnet-4-6"


class LLMSettings(BaseSettings):
    """LLM provider configuration.

    Resolution order at runtime (see ``limen.core.llm_resolver.resolve_provider``):

    1. ``provider`` override (this field) wins.
    2. else ``ANTHROPIC_API_KEY`` → :class:`LLMProvider.ANTHROPIC`.
    3. else ``OPENAI_API_KEY`` → :class:`LLMProvider.OPENAI`.
    4. else Foundry creds → :class:`LLMProvider.FOUNDRY`.
    5. else → :class:`LLMProvider.OLLAMA`.
    """

    model_config = SettingsConfigDict(extra="ignore")

    provider: LLMProvider | None = None
    models: LLMModels = Field(default_factory=LLMModels)
    ollama_base_url: str = "http://localhost:11434"


class SchedulerSettings(BaseSettings):
    """Background scheduling settings."""

    model_config = SettingsConfigDict(extra="ignore")

    cache_cleanup: SchedulerBackend = SchedulerBackend.APSCHEDULER
    cache_cleanup_interval_seconds: int = Field(default=300, ge=10)


class Settings(BaseSettings):
    """Top-level application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    db: DBSettings = Field(default_factory=DBSettings)
    object_store: ObjectStoreSettings = Field(default_factory=ObjectStoreSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = False

    # Workflow toggles
    # `enable_insitu` gates the conditional IoT (sensor_fetch) edge in the
    # MAF workflow. V1 default = False (no IoT). V1.5 will flip this when
    # the real sensor ingestion lands.
    enable_insitu: bool = False

    # Provider credentials are read as *top-level* env vars (no nesting) so the
    # canonical names from each vendor's SDK keep working unchanged.
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    foundry_endpoint: str | None = None
    foundry_api_key: SecretStr | None = None
    azure_ai_endpoint: str | None = None
    azure_ai_api_key: SecretStr | None = None
    anthropic_foundry_endpoint: str | None = None
    anthropic_foundry_api_key: SecretStr | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached :class:`Settings` singleton.

    Callers should always go through this function rather than instantiating
    :class:`Settings` directly so that environment changes during the lifetime
    of a process are intentional.
    """
    return Settings()
