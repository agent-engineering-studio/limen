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
    # Run the MAF workflow for every active AOI every N minutes.
    hourly_monitoring_minutes: int = Field(default=60, ge=5)
    # Run the ISPRA IdroGEO sync every N hours.
    weekly_idrogeo_hours: int = Field(default=24 * 7, ge=1)
    enable_hourly_monitoring: bool = True
    enable_weekly_idrogeo: bool = True


class ApiSettings(BaseSettings):
    """FastAPI server + CORS + OTel exporter settings."""

    model_config = SettingsConfigDict(extra="ignore")

    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1, le=65535)
    # Default CORS is permissive because Phase 5 is intentionally
    # auth-less and serves a public map. Tighten in production via env.
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    pg_tileserv_url: str | None = None
    otel_otlp_endpoint: str | None = None
    otel_service_name: str = "limen-api"


class TelegramChannelSettings(BaseSettings):
    """Telegram bot config. Disabled when ``bot_token`` is empty."""

    model_config = SettingsConfigDict(extra="ignore")

    bot_token: SecretStr | None = None
    chat_id: str | None = None
    parse_mode: Literal["HTML", "MarkdownV2"] = "HTML"
    disable_web_page_preview: bool = True
    api_base_url: str = "https://api.telegram.org"


class MqttChannelSettings(BaseSettings):
    """MQTT publisher config. Disabled when ``broker_host`` is empty."""

    model_config = SettingsConfigDict(extra="ignore")

    broker_host: str | None = None
    broker_port: int = Field(default=1883, ge=1, le=65535)
    topic: str = "limen/alerts"
    username: str | None = None
    password: SecretStr | None = None
    tls: bool = False
    qos: Literal[0, 1, 2] = 1
    client_id: str = "limen-notifier"


class EmailChannelSettings(BaseSettings):
    """SMTP email config. Disabled when ``smtp_host`` or recipients are empty."""

    model_config = SettingsConfigDict(extra="ignore")

    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    username: str | None = None
    password: SecretStr | None = None
    from_address: str | None = None
    recipients: list[str] = Field(default_factory=list)
    use_starttls: bool = True
    use_tls: bool = False
    timeout_seconds: float = Field(default=15.0, gt=0)


class NotificationsSettings(BaseSettings):
    """Top-level notifications block — enabled channels + per-channel config."""

    model_config = SettingsConfigDict(extra="ignore")

    # When the list is empty no channels are constructed; the workflow
    # logs alerts as if `alert_dispatch` were still the V1 stub.
    enabled_channels: list[Literal["telegram", "mqtt", "email"]] = Field(default_factory=list)
    telegram: TelegramChannelSettings = Field(default_factory=TelegramChannelSettings)
    mqtt: MqttChannelSettings = Field(default_factory=MqttChannelSettings)
    email: EmailChannelSettings = Field(default_factory=EmailChannelSettings)


class IotSettings(BaseSettings):
    """V1.5 in-situ ingestion knobs.

    The whole subsystem is gated by :attr:`Settings.enable_insitu`.
    With it off the ingestor never starts, the rollup job never runs,
    and the engine's K component is dormant — the scores are byte-for-
    byte identical to the pure V1 path.
    """

    model_config = SettingsConfigDict(extra="ignore")

    # MQTT broker for the ingestor. Defaults to the demo Mosquitto.
    broker_host: str = "localhost"
    broker_port: int = Field(default=1883, ge=1, le=65535)
    broker_tls: bool = False
    username: str | None = None
    password: SecretStr | None = None
    client_id: str = "limen-iot-ingestor"

    # Topic taxonomy: limen/v1/{region}/{site}/{thing}/{datastream}/obs
    topic_root: str = "limen/v1"
    subscribe_pattern: str = "limen/v1/+/+/+/+/obs"
    lwt_pattern: str = "limen/v1/+/+/+/status"

    # QC range checks per ObservedProperty.
    qc_rainfall_range: tuple[float, float] = (0.0, 200.0)
    qc_pore_pressure_range: tuple[float, float] = (0.0, 1000.0)
    qc_soil_moisture_range: tuple[float, float] = (0.0, 1.0)
    qc_displacement_range: tuple[float, float] = (-50000.0, 50000.0)
    qc_velocity_range: tuple[float, float] = (-2000.0, 2000.0)
    qc_acceleration_range: tuple[float, float] = (-2000.0, 2000.0)
    spike_step_factor: float = Field(default=5.0, gt=0.0)
    flatline_window_minutes: int = Field(default=120, ge=5)
    flatline_min_samples: int = Field(default=12, ge=2)
    gap_threshold_minutes: int = Field(default=60, ge=1)

    # Rollup + partition rollover cadence.
    rollup_minutes: int = Field(default=10, ge=1)
    partition_window_months: int = Field(default=6, ge=1, le=24)


class AlertSettings(BaseSettings):
    """Alert-dispatch rules used by the AlertDispatchExecutor."""

    model_config = SettingsConfigDict(extra="ignore")

    # Minimum :class:`RiskLevel` to dispatch. Stored as a string so
    # operators can override via env without importing the enum.
    min_level: Literal["Low", "Moderate", "High", "VeryHigh"] = "High"
    # Window during which a repeat alert for the same cell is suppressed.
    dedup_window_minutes: int = Field(default=180, ge=0)
    # How many top-priority cells to mention explicitly in the payload.
    top_k: int = Field(default=5, ge=1, le=50)
    # Public map base URL used to build deep links inside the payload.
    map_base_url: str = "http://localhost:5173"


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
    api: ApiSettings = Field(default_factory=ApiSettings)
    notifications: NotificationsSettings = Field(default_factory=NotificationsSettings)
    alert: AlertSettings = Field(default_factory=AlertSettings)
    iot: IotSettings = Field(default_factory=IotSettings)

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
