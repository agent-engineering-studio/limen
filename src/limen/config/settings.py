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

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import RiskLevel


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
    LLAMACPP = "llamacpp"


class ScoringEngineKind(StrEnum):
    """Which scoring engine drives the workflow's authoritative numbers.

    The V1 ``deterministic`` engine remains the default and the champion
    that drives alerts. ``ml`` swaps it for the V2 :class:`MLScoringEngine`
    once a model has been promoted.
    """

    DETERMINISTIC = "deterministic"
    ML = "ml"


class ScoringMode(StrEnum):
    """Champion-challenger mode for the workflow.

    * ``champion_only`` — only the configured engine runs.
    * ``shadow`` — the deterministic engine remains champion (its scores
      drive alerts + persistence), and the ML engine runs in parallel
      with its predictions logged for evaluation only.
    """

    CHAMPION_ONLY = "champion_only"
    SHADOW = "shadow"


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
    tiles_password: SecretStr | None = Field(
        default=None,
        description=(
            "Password del ruolo `limen_tiles` (migrazione 078) con cui si collega "
            "pg_tileserv: l'API la imposta all'avvio. Solo esadecimale "
            "(`openssl rand -hex 24`), perché finisce dentro un URL."
        ),
    )

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
    # Il revisore di fedeltà. Opt-in: il job gira solo se LLM__MODELS__FEDELTA
    # è dichiarato. Va sempre all'API di Claude in batch, mai al gateway: è un
    # id Claude, e non lo stesso modello che scrive le spiegazioni (Haiku).
    fedelta: str = "claude-sonnet-5-5"


class LLMSettings(BaseSettings):
    """LLM provider configuration.

    Resolution order at runtime (see ``limen.core.llm_resolver.resolve_provider``):

    1. ``provider`` override (this field) wins.
    2. else ``ANTHROPIC_API_KEY`` → :class:`LLMProvider.ANTHROPIC`.
    3. else ``OPENAI_API_KEY`` → :class:`LLMProvider.OPENAI`.
    4. else Foundry creds → :class:`LLMProvider.FOUNDRY`.
    5. else → :class:`LLMProvider.LLAMACPP` (the self-hosted inference server).

    Claude therefore stays available but opt-in: setting ``ANTHROPIC_API_KEY``
    *is* the configuration that selects it.

    .. warning::
       The no-credentials fallback changed from Ollama to llama.cpp. A
       deployment that relied on the implicit Ollama fallback — the Aruba VPS,
       which sets only ``LLM__OLLAMA_BASE_URL`` — must now set
       ``LLM__PROVIDER=ollama`` explicitly.
    """

    model_config = SettingsConfigDict(extra="ignore")

    provider: LLMProvider | None = None

    @field_validator("provider", mode="before")
    @classmethod
    def _blank_provider_is_none(cls, v: object) -> object:
        # An empty env var (LLM__PROVIDER=) means "auto-detect", not an
        # invalid enum — coerce blanks to None at the boundary.
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    models: LLMModels = Field(default_factory=LLMModels)
    # Host Ollama (no auth) → http://localhost:11434 (or host.docker.internal
    # from a container). Ollama Cloud → https://ollama.com with ollama_api_key.
    ollama_base_url: str = "http://localhost:11434"
    ollama_api_key: SecretStr | None = None
    # Single Ollama model used for every agent role (the per-role defaults are
    # Claude ids, which Ollama can't serve). Override per host/cloud.
    ollama_model: str = "qwen3.6:latest"
    # Run the RiskAnalyst + Briefing LLM nodes only when the assessment has at
    # least one cell at/above this level (hard escalation always runs them).
    # Local models take minutes per briefing; skipping all-quiet cycles keeps
    # the hourly job inside its hour. "None" = always run.
    briefing_min_level: Literal["None", "Low", "Moderate", "High", "VeryHigh"] = "Moderate"
    # Per-request ceiling for Ollama chat calls. Local models writing a
    # 200-word Italian briefing routinely exceed the shared HTTP client's
    # default timeout, which silently downgraded briefings to the
    # deterministic fallback.
    ollama_timeout_seconds: float = Field(default=300.0, gt=0)

    # ── llama.cpp / llama-swap (self-hosted inference server) ──────────────
    # llama-swap fronts llama-server and loads the requested model on demand,
    # exposing the OpenAI shape at /v1/chat/completions. Point this at the
    # LiteLLM gateway (:8091), not at llama-swap: routing by model name, the
    # spend cap and the local->cloud fallback all live there. The embedding
    # server is a separate process on :8082 — NOT :8081, which on this host is
    # GeoServer.
    # 8091 = the gateway. NOT 8080: that is Limen's own API on the reference
    # host, and pointing the LLM client at it yields a 404 from Limen itself
    # — an engine that "answers" but never generates.
    llamacpp_base_url: str = "http://127.0.0.1:8091"
    # Set only if llama-server was started with --api-key.
    llamacpp_api_key: SecretStr | None = None
    # Logical model id: behind LiteLLM this is a key in the gateway's
    # model_list, not a file name. Fallback for any agent role NOT declared in
    # ``models`` — an undeclared role must not inherit the Claude default,
    # which the gateway would reject.
    llamacpp_model: str = "qwen3.5-9b"
    # Ceiling for a role with no entry in ``llamacpp_role_timeout_seconds``.
    # Sized for the GPU-resident models behind the gateway (fast/chat/extract)
    # on NVMe, where a llama-swap load is seconds — not the ~2 minutes from
    # spinning disk that the old 600 s default was budgeting for.
    #
    # Too high is as harmful as too low, in opposite ways. Too low cuts off a
    # healthy model mid-answer. Too high makes a *broken* engine
    # indistinguishable from a slow one for as long as the ceiling lasts: the
    # caller blocks, falls back to the deterministic text anyway, and the only
    # signal is that the fallback arrived later. The number is "how long a
    # working model can plausibly take", not "how long we will wait".
    llamacpp_timeout_seconds: float = Field(default=120.0, gt=0)
    # Per-role override, keyed by the agent-role label ("Briefing", ...) rather
    # than the env-var name. A role deliberately pointed at a slow model needs
    # its own ceiling, and the others must not inherit it and spend minutes
    # waiting for an error:
    #   LLM__LLAMACPP_ROLE_TIMEOUT_SECONDS='{"Briefing": 5400}'
    llamacpp_role_timeout_seconds: dict[str, float] = Field(default_factory=dict)

    # Cadenza di `briefing_enrichment` (#78). Dieci minuti: il briefing non è
    # più dentro lo sweep, e la finestra fra un tick orario e il successivo è
    # abbastanza larga da assorbire una decina di regioni anche con un modello
    # locale. La finestra di recupero è più lunga dell'ora dello sweep perché
    # un riavvio del worker non deve lasciare regioni senza narrativa.
    briefing_interval_minutes: int = Field(default=10, ge=1)
    briefing_lookback_hours: int = Field(default=3, ge=1)
    # Una regione si rispiega solo se la sua classe dominante è cambiata o
    # dopo queste ore (#155). Senza, ogni sweep orario è uno sweep nuovo e,
    # con tre pericoli e un modello a pagamento, sarebbero fino a 1.440
    # spiegazioni al giorno per dire spesso la stessa cosa. 24 e non 12: il
    # 10 ottobre 2026, 14 riscritture su 18 venivano dal timer e non da un
    # cambio di classe — si pagava due volte al giorno lo stesso racconto.
    # Non oltre: il testo parla di giorni («domenica», «72 ore»), e a 48 ore
    # parlerebbe di giorni già passati.
    briefing_min_hours: int = Field(default=24, ge=1)

    # Quante spiegazioni il revisore rilegge per sera, e a che ora (UTC). Le
    # 21: dopo la previsione per cella delle 20:20, prima della notte.
    fedelta_campione: int = Field(default=4, ge=1)
    fedelta_ora_utc: int = Field(default=21, ge=0, le=23)
    # Quanto il job aspetta il batch prima di annullarlo. Di solito finisce in
    # minuti, ma l'API si riserva fino a 24 ore: oltre questo tetto i verdetti
    # restano a null, come per un revisore che non risponde.
    fedelta_attesa_massima_minuti: int = Field(default=120, ge=1)

    @field_validator("llamacpp_role_timeout_seconds")
    @classmethod
    def _positive_role_timeouts(cls, v: dict[str, float]) -> dict[str, float]:
        bad = sorted(role for role, seconds in v.items() if seconds <= 0)
        if bad:
            raise ValueError(
                "LLM__LLAMACPP_ROLE_TIMEOUT_SECONDS needs a positive ceiling "
                f"for every role; got <= 0 for: {', '.join(bad)}"
            )
        return v


class SchedulerSettings(BaseSettings):
    """Background scheduling settings."""

    model_config = SettingsConfigDict(extra="ignore")

    cache_cleanup: SchedulerBackend = SchedulerBackend.APSCHEDULER
    cache_cleanup_interval_seconds: int = Field(default=300, ge=10)
    # Run the MAF workflow for every active AOI every N minutes.
    hourly_monitoring_minutes: int = Field(default=60, ge=5)
    # Quanto tenere la tracciatura dei job (#75). Novanta giorni: abbastanza
    # per confrontare uno sweep di oggi con quello di due mesi fa — che è il
    # motivo per cui la tabella esiste — e poche migliaia di righe al giorno,
    # quindi nessuna ragione di essere avari.
    job_runs_retention_days: int = Field(default=90, ge=1)
    # Se lo scheduler parte in questo processo (#77). Nel container `api` è
    # `false`: l'API torna HTTP puro e read-only, coerente con la mappa
    # pubblica di #69. Il processo `limen worker` ignora questo flag — è la
    # sua unica ragione di esistere, e un worker che si spegne da solo per
    # una variabile d'ambiente sarebbe un modo silenzioso di fermare i batch.
    enabled: bool = True
    # Quante regioni valutare in parallelo nello sweep. Quattro: il limite non
    # è la CPU (64 core) ma il rate limit di Open-Meteo e la contesa sul
    # database, e con l'LLM che domina il tempo per regione bastano poche
    # regioni concorrenti per riempire l'attesa.
    sweep_concurrency: int = Field(default=4, ge=1, le=32)
    # Il bollettino di criticità DPC: esce entro le 16:00 e a volte si
    # aggiorna dopo, quindi un controllo all'ora. Pubblico, nessuna chiave.
    enable_dpc_bollettini: bool = True
    dpc_bollettini_minutes: int = Field(default=60, ge=10)
    # Terremoti INGV e scuotimento per cella dalle ShakeMap (#284). Spento:
    # accenderlo porta in vita la componente E delle frane (peso 0,15), che
    # finora valeva zero ovunque, e sposta il campione V1. Il backtest della
    # #287 dice di non farlo: sulla sequenza 2016-17 nessuna frana in più, e
    # fino a ventitré volte le ore-cella in allerta.
    enable_ingv_sync: bool = False
    ingv_sync_minutes: int = Field(default=60, ge=10)
    # Acceso ma fermo da più di così, lo sweep lo dice (#287): E additiva
    # sbaglia al più di 0,15, ma tornare a zero in silenzio in piena sequenza
    # sismica è lo stesso guasto rassicurante della #143.
    ingv_sync_ritardo_massimo_minuti: int = Field(default=180, ge=30)
    #: Ovest, sud, est, nord: il riquadro del portale ShakeMap INGV.
    ingv_bbox: tuple[float, float, float, float] = (5.0, 35.0, 20.0, 49.0)
    # Run the ISPRA IdroGEO sync every N hours.
    weekly_idrogeo_hours: int = Field(default=24 * 7, ge=1)
    # Hot-table partition maintenance + retention. Partitions are created a
    # week ahead, so anything well under that is safe; 6 h keeps retention
    # responsive without hammering the catalogue.
    partitions_interval_hours: int = Field(default=6, ge=1)
    # Ora UTC della pipeline notturna (#78): shadow ML, drift, retrain,
    # forecast history, partizioni, retention. Le due del mattino perché è
    # dopo l'ultimo sweep della notte e prima del report delle sei.
    nightly_hour_utc: int = Field(default=2, ge=0, le=23)
    # Il tetto del giorno per l'API pubblica GloFAS (#200), su 10.000: la
    # notte ne toglie la previsione dei fiumi dello sweep (un nodo con fiume
    # = una chiamata al giorno, per ogni regione che lo vede) e spende il
    # resto nella portata ordinaria dei nodi, ~52 chiamate a nodo. A tabella
    # vuota sono ~150 nodi a notte, poi meno man mano che la previsione
    # cresce. Il margine di 2.000 è per la previsione delle onde e i rilanci.
    glofas_chiamate_per_notte: int = Field(default=8000, ge=0)
    # La previsione per cella (+24/+48/+72), quattro volte al giorno e non
    # una: calcolata una volta a notte restava in mappa per 24 ore. Il 7
    # ottobre 2026 dava la Basilicata «molto alto» per l'incendio di sabato
    # con il meteo delle 2 di notte, mentre i modelli del mattino portavano
    # pioggia e umidità all'84 % — rifatta con quelli, sabato valeva zero.
    # Venti minuti dopo le ore sinottiche: le corse dei modelli arrivano
    # qualche ora dopo, e la corsa precedente è comunque la più recente.
    forecast_cells_hours_utc: list[int] = Field(default=[2, 8, 14, 20])
    forecast_cells_minute: int = Field(default=20, ge=0, le=59)
    enable_hourly_monitoring: bool = True
    enable_weekly_idrogeo: bool = True


class ApiSettings(BaseSettings):
    """FastAPI server + CORS + OTel exporter settings."""

    model_config = SettingsConfigDict(extra="ignore")

    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1, le=65535)
    # Jolly, dopo la rimozione dell'auth (#69). Le origini esplicite non erano
    # una protezione dei dati: erano il vincolo che il browser impone al CORS
    # **credenziato**, e le credenziali esistevano solo per il cookie di
    # sessione. Le API sono una mappa pubblica in sola lettura, quindi elencare
    # i domini sarebbe una cosa in più da sbagliare al deploy senza niente in
    # cambio. Chi vuole restringere lo fa con API__CORS_ORIGINS; l'esposizione
    # vera resta governata dal binding su loopback + reverse proxy.
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    # Path prefix a reverse proxy strips before forwarding. Empty when the
    # app owns its hostname. Set it (e.g. ``/limen``) when the app is served
    # under a prefix: FastAPI then advertises ``/limen/openapi.json`` in the
    # docs page instead of ``/openapi.json``, which would 404 behind the
    # proxy. It does NOT change the routes the app matches.
    root_path: str = ""
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


class WebhookChannelSettings(BaseSettings):
    """Generic webhook POST (e.g. OpenClaw ``/hooks``). Disabled when ``url`` is empty."""

    model_config = SettingsConfigDict(extra="ignore")

    url: str | None = None
    token: SecretStr | None = None


class RateLimitSettings(BaseSettings):
    """Quanto può uscire, e cosa succede oltre (issue #59).

    Il limite è **per canale**: Telegram e la posta hanno soglie di tolleranza
    diverse, e un unico contatore condiviso farebbe tacere il canale lento per
    colpa di quello veloce.
    """

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    # Messaggi in uscita per canale nell'ultima ora, oltre i quali si accoda.
    # Sei: un centro operativo può leggere un messaggio ogni dieci minuti
    # senza smettere di leggerli.
    max_per_hour: int = Field(default=6, ge=0)
    # Classe oltre la quale il limite non si applica. Il digest è una risposta
    # al volume, non alla gravità.
    bypass_level: Literal["Low", "Moderate", "High", "VeryHigh"] = "VeryHigh"
    # Ogni quanto la coda viene svuotata in un messaggio riepilogativo.
    digest_interval_minutes: int = Field(default=60, ge=5)
    # Età oltre la quale una voce in coda si scarta invece di spedirla: un
    # riepilogo di allerte di ieri è disinformazione, non ritardo.
    digest_max_age_minutes: int = Field(default=360, ge=10)


class NotificationsSettings(BaseSettings):
    """Top-level notifications block — enabled channels + per-channel config."""

    model_config = SettingsConfigDict(extra="ignore")

    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)

    # When the list is empty no channels are constructed; the workflow
    # logs alerts as if `alert_dispatch` were still the V1 stub.
    enabled_channels: list[Literal["telegram", "mqtt", "email", "webhook"]] = Field(
        default_factory=list
    )
    telegram: TelegramChannelSettings = Field(default_factory=TelegramChannelSettings)
    mqtt: MqttChannelSettings = Field(default_factory=MqttChannelSettings)
    email: EmailChannelSettings = Field(default_factory=EmailChannelSettings)
    webhook: WebhookChannelSettings = Field(default_factory=WebhookChannelSettings)


class SensoriRegistrazioneSettings(BaseSettings):
    """Il modulo pubblico di registrazione dei sensori (#253, epic #247).

    Chiuso finché un operatore non lo apre: una richiesta non crea niente, ma
    promette una risposta. La mail va a ``CONTRIBUTI__DESTINATARI``, cioè a chi
    cura il progetto, che approva dalla CLI. Non va aperto finché pg_tileserv
    si collega come `limen` invece che come `limen_tiles` (#269): pubblicherebbe
    `sensor_devices` con la posizione esatta.
    """

    model_config = SettingsConfigDict(extra="ignore")

    aperta: bool = False
    # Dispositivi per registrante, contando le richieste in attesa e i
    # dispositivi revocati: revocare non libera un posto, o la quota si
    # aggirerebbe facendosi revocare.
    max_dispositivi_per_registrante: int = Field(default=3, ge=1)
    max_per_ip_ora: int = Field(default=3, ge=1)
    max_totali_ora: int = Field(default=20, ge=1)
    # Il modulo ha una CSR da incollare: sotto questo tempo l'ha riempito un
    # programma.
    secondi_minimi: float = Field(default=20.0, ge=0.0)
    max_foto_kb: int = Field(default=1024, ge=1)
    # Lo script della CA, dalla radice del repo: la CLI gira sull'host, dove sta
    # la chiave della CA, mai in un container.
    ca_script: str = "scripts/sensori_ca.sh"
    giorni_certificato: int = Field(default=730, ge=1)
    # Dove si collega il dispositivo, scritto nella mail di approvazione.
    broker_pubblico: str = "mqtts://limen.agentengineering.it:8883"
    # Il webhook di The Things Network, scritto nella mail di un sensore
    # LoRaWAN (#266).
    webhook_ttn_pubblico: str = "https://limen.agentengineering.it/sensori/v2/ttn"


class IotCittadiniSettings(BaseSettings):
    """Ingestore del protocollo v2 sul broker dei sensori (#252, epic #247).

    È il kill switch dei dispositivi di terzi: spento, nessun messaggio v2
    entra. Gira solo nel `worker`, mai nell'API pubblica. Le misure che fa entrare
    non toccano lo scoring finché il dispositivo non è di livello 2 (#251).
    """

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = False
    # Il broker dei sensori (#260): mTLS con il certificato dell'ingestore,
    # firmato dalla CA privata. Dentro la rete docker il nome è quello del
    # container, che è nel SAN del certificato del server.
    broker_host: str = "limen-mosquitto-sensori"
    broker_port: int = Field(default=8883, ge=1, le=65535)
    cafile: str = "/run/limen-sensori/ca.crt"
    certfile: str = "/run/limen-sensori/ingestore.crt"
    keyfile: str = "/run/limen-sensori/ingestore.key"
    client_id: str = "limen-ingestore-v2"
    # Password di `limen_ingestore` (migrazione 079, #267): con questa
    # l'ingestore scrive col ruolo ristretto invece che con quello del worker.
    # Solo esadecimale (`openssl rand -hex 24`): finisce nel DSN. Vuota ⇒ il
    # pool principale, com'era.
    db_password: SecretStr | None = None

    # Guardrail. Il broker tronca già a 4096 byte (`max_packet_size`).
    max_payload_bytes: int = Field(default=2048, ge=64)
    # Un orologio avanti di più di così è un dispositivo senza NTP: il
    # messaggio si rifiuta, perché non si sa a che ora si riferisce.
    tolleranza_futuro_secondi: int = Field(default=120, ge=0)
    # Più vecchia di così una misura è «in ritardo»: si salva ma non entra nel
    # rollup che alimenta lo scoring.
    ritardo_minuti: int = Field(default=15, ge=1)
    # Oltre quest'età il messaggio si rifiuta come uno dal futuro: un
    # arretrato di settimane è un orologio rotto, non una rete caduta, e
    # cadrebbe fuori dalle partizioni facendo perdere anche le righe buone.
    max_ritardo_giorni: int = Field(default=30, ge=1)
    # Messaggi al minuto per dispositivo; oltre si scartano. Una lettura ogni
    # cinque secondi è già più di quanto serva a un pluviometro.
    max_messaggi_al_minuto: int = Field(default=12, ge=1)
    # Messaggi scartati per frequenza, nell'ultima ora, prima della quarantena:
    # un firmware in loop si ferma senza toccare gli altri dispositivi.
    scarti_per_quarantena: int = Field(default=60, ge=1)
    # Dopo una riconnessione il broker consegna in pochi secondi tutto ciò che
    # ha tenuto per l'ingestore (#273): per un dispositivo sono minuti di
    # messaggi nello stesso minuto d'arrivo. Per questa finestra un messaggio
    # le cui misure sono tutte anteriori alla connessione è arretrato e non
    # passa dal limite al minuto. La finestra limita quanto un dispositivo
    # possa approfittarne datando indietro le misure.
    grazia_arretrato_minuti: int = Field(default=10, ge=0)
    # Ingresso HTTP firmato (#265), per chi non tiene una sessione MQTT: un
    # listener nel worker, mai nell'API pubblica, dietro nginx. Spento finché
    # non lo si accende; il kill switch resta `enabled`, che lo spegne con
    # l'MQTT. Nel container si ascolta su 0.0.0.0 e la porta si pubblica solo
    # sul loopback (docker-compose.sensori-worker.yml).
    http_attivo: bool = False
    http_host: str = "127.0.0.1"
    http_porta: int = Field(default=8087, ge=1, le=65535)
    # Quanto può distare dall'arrivo il tempo dentro la firma: oltre, la firma
    # è vecchia (un replay) o l'orologio è rotto. La sequenza resta l'altro
    # muro contro i replay, dentro la finestra.
    finestra_firma_secondi: int = Field(default=300, ge=10)
    # Un uplink del webhook TTN (#266) porta i metadati di ogni gateway che
    # l'ha ricevuto: qualche KB, non i 50 byte della misura.
    ttn_max_corpo_bytes: int = Field(default=65536, ge=1024)
    registrazione: SensoriRegistrazioneSettings = Field(
        default_factory=SensoriRegistrazioneSettings
    )


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
    # Il livello è riferito allo zero dell'idrometro, che può stare sopra il
    # pelo dell'acqua in magra: un valore negativo è una misura, non un guasto.
    qc_water_level_range: tuple[float, float] = (-20.0, 50.0)
    qc_air_temperature_range: tuple[float, float] = (-40.0, 55.0)
    qc_relative_humidity_range: tuple[float, float] = (0.0, 100.0)
    qc_wind_speed_range: tuple[float, float] = (0.0, 250.0)
    spike_step_factor: float = Field(default=5.0, gt=0.0)
    flatline_window_minutes: int = Field(default=120, ge=5)
    flatline_min_samples: int = Field(default=12, ge=2)
    gap_threshold_minutes: int = Field(default=60, ge=1)
    # Oltre quest'età l'ultimo aggregato di una cella non è più una misura e
    # la cella torna al modello (#262): senza, un pluviometro guasto dopo
    # uno zero terrebbe M bassa per sempre, e un estensimetro tacitato dopo
    # un'ora in accelerazione terrebbe acceso `hard_escalation`.
    max_age_minutes: int = Field(default=120, ge=10)

    cittadini: IotCittadiniSettings = Field(default_factory=IotCittadiniSettings)

    # Rollup + partition rollover cadence.
    rollup_minutes: int = Field(default=10, ge=1)
    partition_window_months: int = Field(default=6, ge=1, le=24)


class ScoringSettings(BaseSettings):
    """Selects the scoring engine + champion-challenger mode (V2)."""

    model_config = SettingsConfigDict(extra="ignore")

    engine: ScoringEngineKind = ScoringEngineKind.DETERMINISTIC
    mode: ScoringMode = ScoringMode.CHAMPION_ONLY
    # MLflow tracking — sqlite for the dev default (MLflow >=3.13 rejects the
    # legacy ./mlruns file store), postgresql:// for prod
    # (the project's Postgres can host the MLflow backend, avoiding a
    # separate database). Artifacts go to the ObjectStore root by default.
    mlflow_tracking_uri: str = "sqlite:///mlflow.db"
    # Dove un esperimento NUOVO tiene gli artefatti (#302). Vuoto = il default
    # di MLflow, `./mlruns` della cartella di lavoro: nel container è /app,
    # che non è montato, e gli artefatti sparirebbero al primo rebuild. Il
    # compose lo punta a file:///var/lib/limen/mlruns, montato dalla radice
    # dati. Un esperimento che esiste già resta dov'è.
    mlflow_artifact_root: str = ""
    mlflow_experiment: str = "limen-landslide"
    mlflow_registered_model: str = "limen-landslide-ml"
    # Shadow rows older than this are purged by the cleanup job — the
    # national hourly sweep writes ~1M rows/day (~1 GB/day). 0 = keep all.
    model_runs_retention_days: int = Field(default=30, ge=0)
    # Quante celle per regione ricevono l'attribuzione SHAP nel challenger
    # (#76). L'attribuzione per cella è il costo dominante dello shadow, e su
    # 312.000 celle produce spiegazioni che nessuno leggerà: chi apre il
    # dettaglio lo fa per le celle che contano. Le altre prendono il ripiego
    # sulle magnitudini, che è il percorso già previsto quando l'explainer
    # manca. 0 disattiva lo SHAP del tutto.
    shadow_shap_top_k: int = Field(default=50, ge=0)
    # Hot-table retention for per-cell assessments (~15 GB/day nationally).
    # mv_latest_risk + alert ledgers keep the operational state. 0 = keep all.
    assessments_retention_days: int = Field(default=14, ge=0)
    # Quando una cella merita una riga di storico (#135). Lo sweep orario
    # scriveva ogni cella a ogni giro — ~19 milioni di righe al giorno — e la
    # maggioranza diceva la stessa cosa dell'ora prima: con il 70% delle
    # celle in classe «Nessuno» per distribuzione obiettivo, il volume era
    # quasi tutto fermo. Lo stato corrente vive in `latest_risk` dal #125,
    # quindi lo storico può registrare i cambiamenti invece dei fotogrammi.
    #
    # `history_min_delta` è lo scostamento di punteggio sotto il quale due
    # calcoli sono la stessa notizia: 0,02 su una scala 0-1 sta sotto la
    # risoluzione visibile della spezzata del trend. 0 = scrivi sempre, cioè
    # il comportamento di prima.
    history_min_delta: float = Field(default=0.02, ge=0.0, le=1.0)
    # Il battito: anche una cella immobile lascia una traccia ogni tanto.
    # Senza, la retention le farebbe scadere l'ultima riga e la sua storia si
    # azzererebbe — il trend mostrerebbe il vuoto dove c'è la calma.
    history_heartbeat_hours: int = Field(default=24, ge=1)
    # Oltre questa dimensione il passo notturno avvisa che il database sta
    # crescendo verso il bordo del volume. 0 = nessun avviso: la soglia
    # dipende dal disco del deployment, e un default inventato qui sarebbe
    # sbagliato ovunque tranne che su una macchina.
    db_size_warn_gb: int = Field(default=0, ge=0)
    mlflow_model_stage: Literal["Staging", "Production", "Archived"] = "Production"
    # Promotion gate — the ML model is blocked from champion until it
    # clears these floors on the same backtest the V1 baseline ran on.
    promotion_auc_pr_min: float = Field(default=0.55, ge=0.0, le=1.0)
    promotion_brier_max: float = Field(default=0.20, ge=0.0, le=1.0)
    promotion_hit_rate_min: float = Field(default=0.70, ge=0.0, le=1.0)
    promotion_far_max: float = Field(default=0.30, ge=0.0, le=1.0)
    promotion_lead_time_hours_min: float = Field(default=18.0, ge=0.0)


class HazardsSettings(BaseSettings):
    """Which hazards the application scores.

    The database has its own copy in the ``hazards`` table, because
    ``mv_latest_risk`` cross-joins it and a view cannot read settings. The two
    are checked for drift at startup and a mismatch is a warning, not a
    refusal: during a deploy one side moves first, and the public map must
    keep serving.
    """

    model_config = SettingsConfigDict(extra="ignore")

    # Tutti e tre, dalla Fase 3 (#63): ognuno ha motore, configurazione e
    # workflow. `check_scorable` li verifica comunque a ogni avvio, così un
    # deployment che ne toglie uno lo scopre lì e non a metà sweep.
    enabled: list[HazardType] = Field(
        default_factory=lambda: [DEFAULT_HAZARD, HazardType.WILDFIRE, HazardType.FLOOD]
    )


class TrainingSettings(BaseSettings):
    """Feature-store + training pipeline knobs (V2)."""

    model_config = SettingsConfigDict(extra="ignore")

    # Background (negative) sample density — multiplier over positive count.
    background_ratio: float = Field(default=5.0, gt=0.0)
    # Spatial-block grid edge (degrees) — coarse enough that nearby cells
    # don't end up in different folds. 0.5° ≈ 50 km in southern Italy.
    spatial_block_deg: float = Field(default=0.5, gt=0.0, le=2.0)
    spatial_cv_folds: int = Field(default=5, ge=2, le=10)
    # Feature QA: drop the later feature of any pair with |Pearson r|
    # above this before training (SHAP credit otherwise splits across
    # collinear twins). 1.0 disables pruning.
    collinearity_prune_r: float = Field(default=0.95, gt=0.0, le=1.0)
    # Optuna search.
    optuna_trials: int = Field(default=50, ge=1, le=2000)
    optuna_timeout_seconds: int = Field(default=900, ge=10)
    seed: int = Field(default=42, ge=0)
    # Riaddestramento automatico quando il drift lo chiede (#78). Default
    # **false**: addestrare da soli è accettabile, promuovere no, e finché
    # l'operatore non guarda il tag di promozione un modello nuovo è solo
    # un run MLflow in più. Acceso, gira in un sottoprocesso `uv run limen
    # train` — Optuna non condivide il processo del worker.
    auto_retrain: bool = False


class EgmsSettings(BaseSettings):
    """Copernicus EGMS, prodotto Ortho L3: la velocità media del terreno a 100 m.

    Fail-closed. Due credenziali, la prima vince:

    * ``EGMS__SERVICE_KEY`` — il JSON della chiave di servizio CLMS (profilo su
      land.copernicus.eu → «API Tokens»). Non scade: ogni sync fa le sue
      ricerche, e il passo notturno sa quando esce una release nuova;
    * ``EGMS__TOKEN`` — l'``id`` copiato da un link dell'EGMS Explorer. È l'id
      di una ricerca, e **scade**: va bene per un sync a mano.
    """

    model_config = SettingsConfigDict(extra="ignore")

    service_key: SecretStr | None = None
    token: SecretStr | None = None
    archive_url: str = "https://egms.land.copernicus.eu/insar-api/archive"
    #: La finestra della release: cinque anni, una release all'anno.
    release: str = "2020_2024"
    #: Dove tenere i GeoTIFF delle tile (~4 MB l'uno, due per tile).
    cartella: str = "/tmp/limen-egms"

    @property
    def attivo(self) -> bool:
        return any(
            v is not None and bool(v.get_secret_value().strip())
            for v in (self.service_key, self.token)
        )


class CopernicusSettings(BaseSettings):
    """L'Early Warning Data Store di Copernicus (EWDS): GloFAS.

    Fail-closed come FIRMS: senza ``COPERNICUS__EWDS_KEY`` la previsione di
    portata resta sull'API pubblica di Open-Meteo, com'era. La chiave è
    gratuita (account ECMWF) e la licenza CEMS-Floods va accettata una volta
    sul sito.
    """

    model_config = SettingsConfigDict(extra="ignore")

    ewds_url: str = "https://ewds.climate.copernicus.eu/api"
    ewds_key: SecretStr | None = None
    #: Dove tenere i file delle corse scaricate (pochi centinaia di KB l'una).
    cartella: str = "/tmp/limen-ewds"
    #: Quanto aspettare la coda dell'EWDS prima di rinunciare per questo giro.
    #: Il download non si interrompe: il file arriva e il giro dopo lo trova.
    attesa_massima_secondi: int = Field(default=900, ge=60)
    #: Oltre questa età la corsa salvata non vale più come previsione, e il
    #: ramo fluviale torna a chiedere a Open-Meteo.
    eta_massima_giorni: int = Field(default=2, ge=1)

    @property
    def attivo(self) -> bool:
        return self.ewds_key is not None and bool(self.ewds_key.get_secret_value())


class RadarArchiveSettings(BaseSettings):
    """L'archivio locale del radar DPC «Merging» (corretto con i pluviometri).

    L'API pubblica del DPC tiene circa cinque mesi: quello che non si salva
    in tempo si perde, e lo storico che serve al backtest e alle verifiche
    sparisce un mese alla volta. Vuoto ``RADAR_ARCHIVE__CARTELLA`` = il passo
    notturno non fa niente, come ogni sorgente non configurata.
    """

    model_config = SettingsConfigDict(extra="ignore")

    cartella: str = ""
    #: Quanto indietro guarda il passo: oltre quello che il DPC tiene ancora
    #: (~150 giorni) le richieste rispondono 403 e si contano come perse.
    giorni: int = Field(default=160, ge=1)
    #: File scaricati al massimo per notte: il primo giro recupera i mesi già
    #: pubblicati in poche notti senza tenere ferma la pipeline.
    file_per_notte: int = Field(default=1500, ge=1)

    @property
    def attivo(self) -> bool:
        return bool(self.cartella)


class BackupSettings(BaseSettings):
    """Il backup notturno dello stato, fuori dal server (#304).

    Ha il suo object store, separato da quello dell'app: il backup deve
    sopravvivere al server, e un errore di configurazione dell'app non deve
    poterlo cancellare. Vuoti ``BACKUP__BUCKET`` e ``BACKUP__ROOT`` = il passo
    notturno si salta, e lo dice.
    """

    model_config = SettingsConfigDict(extra="ignore")

    backend: ObjectStoreBackend = ObjectStoreBackend.S3
    #: Solo per ``backend=filesystem``: utile in prova, non protegge da un
    #: guasto della macchina.
    root: Path | None = None
    bucket: str | None = None
    prefix: str = "limen"
    region: str | None = None
    endpoint_url: str | None = None
    access_key_id: SecretStr | None = None
    secret_access_key: SecretStr | None = None

    #: I backup più vecchi si cancellano, ma gli ultimi ``tieni_almeno``
    #: restano sempre: un notturno fermo per un mese non deve svuotare il bucket.
    retention_giorni: int = Field(default=30, ge=1)
    tieni_almeno: int = Field(default=3, ge=1)
    #: Oltre questa età dell'ultimo backup riuscito lo sweep orario avvisa.
    eta_massima_ore: int = Field(default=36, ge=1)
    #: Tabelle di cui si salva solo lo schema (pattern di ``pg_dump``): calde,
    #: derivate o ricaricabili dalle sorgenti. Misurate il 2026-10-24: ~29 GB
    #: di 31, contro ~2 GB di stato.
    solo_schema: tuple[str, ...] = (
        "public.risk_assessments*",
        "public.model_runs*",
        "public.latest_risk",
        "public.latest_forecast*",
        "public.rain_ens_forecast",
        "public.app_cache",
        "public.pai_hazard*",
        "public.flood_hazard*",
        "public.iffi_landslides",
        "public.osm_infrastructure",
    )
    #: Tabelle escluse del tutto (pattern di ``pg_dump``), schema compreso.
    escluse: tuple[str, ...] = ("public.tmp_*",)
    #: Cartelle salvate come tar.gz accanto al dump (per esempio ``mlruns``),
    #: separate da virgola.
    cartelle: str = ""
    #: Prefisso dei comandi PostgreSQL. Vuoto nel worker, che ha il client;
    #: ``docker exec -i limen-postgres`` dall'host, dove pg_dump non c'è.
    comando_pg: str = ""
    #: La connessione vista da ``pg_dump``: vuota = ``DB__CONNECTION_STRING``.
    #: Con ``comando_pg`` dentro un container serve quella del container.
    dsn: SecretStr | None = None
    #: La passphrase che cifra la CA dei sensori (#304). Sta nel .env
    #: dell'host, e una copia fuori dal server: senza, il backup non si apre.
    passphrase_ca: SecretStr | None = None
    #: La CA da salvare: vuota = ``$LIMEN_SENSORI_DIR/ca``.
    cartella_ca: Path | None = None
    #: Le versioni di ``dataset_versions`` (``sorgente:dataset``, LIKE) delle
    #: tabelle solo schema: dopo un ripristino si dimenticano, o il loader
    #: direbbe «già caricato» e le lascerebbe vuote.
    versioni_da_dimenticare: tuple[str, ...] = ("geoserver:flood:%", "osm:%", "ispra:idrogeo")
    #: Un backup con meno di questa frazione delle righe di stato del
    #: precedente sospende la retention: un volume ricreato vuoto non deve
    #: far uscire dal bucket i backup buoni.
    soglia_crollo: float = Field(default=0.5, gt=0.0, le=1.0)

    @field_validator("passphrase_ca", mode="before")
    @classmethod
    def _passphrase_vera(cls, v: object) -> object:
        # `BACKUP__PASSPHRASE_CA=` scommentata vuota cifrerebbe la CA con la
        # stringa vuota, cioè in chiaro su un bucket di terzi.
        testo = v.get_secret_value() if isinstance(v, SecretStr) else v
        if testo in (None, ""):
            return None
        if isinstance(testo, str) and len(testo) < 20:
            raise ValueError("BACKUP__PASSPHRASE_CA: almeno 20 caratteri")
        return v

    @property
    def attivo(self) -> bool:
        if self.backend is ObjectStoreBackend.FILESYSTEM:
            return self.root is not None
        return bool(self.bucket)


class OpenMeteoSettings(BaseSettings):
    """Dove chiedere il meteo (#142).

    Vuote, si usano gli endpoint pubblici e non cambia niente. Valorizzate,
    puntano a un'istanza Open-Meteo propria — che e' open source e gira in
    Docker, quindi rispetta l'invariante "self-hosted, nessun cloud" fino in
    fondo e toglie il tetto di 10.000 chiamate al giorno che ha spento
    alluvione e incendio su tutta l'Italia.

    **Portata e onde restano fuori di proposito.** GloFAS non e' pubblicato
    sul bucket AWS di Open-Meteo -- "climate, flood, satellite and ensemble
    models are not published due to their immense size" -- quindi il ramo
    fluviale non si puo' auto-ospitare comunque; e il moto ondoso e' un solo
    scalare per AOI, venti chiamate l'ora, che non e' mai stato il problema.
    Dare loro una manopola sarebbe la messa in conto del futuro che questo
    progetto vieta.
    """

    model_config = SettingsConfigDict(extra="ignore")

    #: Sostituisce `https://api.open-meteo.com/v1/forecast`. Da qui passano
    #: le due griglie grosse -- FWI e pioggia per nodo -- piu' quella
    #: pluviale dell'alluvione: e' il 95 % del traffico.
    forecast_url: str | None = None
    #: Sostituisce `https://archive-api.open-meteo.com/v1/archive`. Serve al
    #: backfill della catena FWI e ai backtest, non allo sweep.
    archive_url: str | None = None
    #: Il modello da nominare nelle richieste. Un'istanza propria serve solo
    #: i modelli che ha sincronizzato e non sa scegliere da se' come fa
    #: `best_match` sull'API pubblica: senza questo risponde a vuoto.
    #: Per l'Italia `dwd_icon_eu` (7 km, umidita' del suolo e neve comprese);
    #: per l'archivio il sync e' `copernicus_era5_land`.
    models: str | None = None


class MonitoringSettings(BaseSettings):
    """Drift + retraining monitor cadence + thresholds (V2)."""

    model_config = SettingsConfigDict(extra="ignore")

    psi_warn: float = Field(default=0.1, ge=0.0)
    psi_alert: float = Field(default=0.25, ge=0.0)
    ks_alert: float = Field(default=0.2, ge=0.0)
    prediction_drift_alert: float = Field(default=0.15, ge=0.0)
    # APScheduler cadence — coarse, drift checks aren't a hot path.
    drift_check_hours: int = Field(default=24, ge=1)
    enable_drift_monitoring: bool = True
    # Canonical feature whose distribution is compared training-vs-live.
    # Must exist both in training_samples.features and in the shadow's
    # persisted breakdown["features"] (same keys, same scales).
    drift_feature: str = "rain.rain_72h_mm"


class GeodataSettings(BaseSettings):
    """Hooks into the V2 Geo-Data Service (§3.3.4-ter).

    The geodata stack itself runs in its own compose profile — these
    settings only control when the *operational* API refreshes its
    per-cell static factors against the geodata PostGIS via
    ``limen geodata export-features``.

    Default off: the geodata profile is opt-in, so the operational API
    never assumes it's running.
    """

    model_config = SettingsConfigDict(extra="ignore")

    enable_periodic_export: bool = False
    """When true, the scheduler runs ``export_cell_features`` periodically."""
    export_features_hours: int = Field(default=168, ge=1)
    """Cadence (hours). 168 = weekly. The PAI + IFFI datasets refresh
    yearly at most — daily would be wasteful."""


class GeoServerSourceSettings(BaseSettings):
    """GeoServer PostGIS as the authoritative source of ISPRA static data.

    When ``db_dsn`` is set, ``limen geoserver-sync`` (and the
    ``bootstrap-static`` path) load the IFFI landslide inventory and the
    PAI hazard mosaic from the GeoServer-backed PostGIS into the
    operational ``iffi_landslides`` / ``pai_hazard`` tables, replacing the
    IdroGeo WFS ingest as the source. Off by default (DSN unset) so the
    operational API never assumes the GeoServer stack is running.
    """

    model_config = SettingsConfigDict(extra="ignore")

    # DSN of the GeoServer PostGIS (the mcp-geo-server stack, port 55433 on
    # the same host). None ⇒ the loader is a clean no-op.
    db_dsn: str | None = None
    # PostGIS schema holding the published feature tables.
    schema_name: str = "public"


class KgSettings(BaseSettings):
    """Knowledge-graph sidecar (V2.x advisory grounding).

    Off by default. The deterministic scoring path runs unchanged when
    the KG is disabled; with it enabled, the BriefingAgent calls the
    sidecar via :mod:`limen.agents.grounding.kg_client` with a short
    timeout and caches results in ``app_cache``. KG failures NEVER
    block the workflow and NEVER alter numeric scores.
    """

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = False
    # REST endpoint of the knowledge-graph FastAPI service (the project's
    # sidecar). MCP is also supported via the same transport layer.
    base_url: str = "http://localhost:8000"
    # Stable thread id under which the landslide corpus is ingested.
    thread_id: str = "landslide-kb"
    # Short timeout — the briefing must NEVER stall on KG latency.
    timeout_seconds: float = Field(default=3.0, gt=0.0, le=30.0)
    # How long a (region, mechanism) grounding result stays cached.
    cache_ttl_seconds: int = Field(default=3600, ge=60, le=86_400)
    # Optional bearer token for the KG sidecar (None ⇒ unauthenticated).
    api_token: SecretStr | None = None
    # Top-K passages to ask for; the BriefingAgent surfaces the first N.
    top_k: int = Field(default=4, ge=1, le=20)


class AlertSettings(BaseSettings):
    """Alert-dispatch rules used by the AlertDispatchExecutor."""

    model_config = SettingsConfigDict(extra="ignore")

    # Minimum :class:`RiskLevel` to dispatch. Stored as a string so
    # operators can override via env without importing the enum.
    # Default Moderate: the §2.5 gauge-rain validation measured that real
    # landslides reach High in only ~3% of cases even with perfect rain, so a
    # High-only pipeline is effectively silent. Sub-High dispatches are gated
    # by `min_static_s` below to keep them selective.
    min_level: Literal["Low", "Moderate", "High", "VeryHigh"] = "Moderate"
    # Below-High cells must also sit on a genuinely susceptible slope
    # (S component ≥ this) to alert — "moderate rain on a susceptible slope",
    # not "moderate rain anywhere". High/VeryHigh and hard escalation bypass.
    min_static_s: float = Field(default=0.5, ge=0.0, le=1.0)
    # Window during which a repeat alert for the same cell is suppressed.
    dedup_window_minutes: int = Field(default=180, ge=0)
    # How many top-priority cells to mention explicitly in the payload.
    top_k: int = Field(default=5, ge=1, le=50)
    # Public map base URL used to build deep links inside the payload.
    map_base_url: str = "http://localhost:5173"


class ForecastSettings(BaseSettings):
    """Scheduled predictive runs (event-driven pipeline). ON by default."""

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    # Predictive horizon: score at now + this many hours with forecast rain.
    horizon_hours: int = Field(default=48, ge=1, le=384)
    # How often the scheduled job re-runs the forecast sweep.
    interval_hours: int = Field(default=6, ge=1)
    # Minimum champion level a forecast cell must reach to trigger an alert.
    min_level: Literal["Low", "Moderate", "High", "VeryHigh"] = "High"
    # Repeat predictive alerts for the same (AOI, horizon) are suppressed
    # inside this window — coarser than the operational per-cell dedup.
    dedup_window_hours: int = Field(default=24, ge=0)
    # Optional cap on cells per AOI (smoke/dev); None = full grid.
    cell_limit: int | None = None


class NowcastSettings(BaseSettings):
    """DPC radar (SRI) nowcast trigger. ON by default."""

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    # How often the radar sweep polls the latest SRI frame.
    interval_minutes: int = Field(default=15, ge=5)
    # Rain intensity (mm/h) that counts as a trigger signal.
    min_intensity_mmh: float = Field(default=30.0, gt=0)
    # At least this many 1 km pixels over threshold inside the AOI bbox
    # (a single hot pixel is usually radar clutter).
    min_pixels: int = Field(default=3, ge=1)
    # Skip AOIs whose latest assessment is fresher than this.
    cooldown_minutes: int = Field(default=45, ge=0)


class FirmsSettings(BaseSettings):
    """NASA FIRMS active-fire hotspots (VIIRS 375 m / MODIS 1 km, NRT).

    Fail-closed: without ``FIRMS__MAP_KEY`` the feed is inert — the free
    key is per-user, so there is no sensible default to fall back on.
    """

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    map_key: SecretStr | None = None
    # NRT latency is ~3 h, so polling faster buys nothing.
    interval_minutes: int = Field(default=45, ge=5)
    sources: list[str] = Field(
        default_factory=lambda: [
            "VIIRS_SNPP_NRT",
            "VIIRS_NOAA20_NRT",
            "VIIRS_NOAA21_NRT",
        ]
    )
    # FIRMS caps the area endpoint at 1..5 trailing days per request.
    day_range: int = Field(default=1, ge=1, le=5)
    # VIIRS reports a category; MODIS a 0..100 percentage. Industrial
    # flares and sun glint show up mostly as low-confidence detections.
    min_confidence: Literal["low", "nominal", "high"] = "nominal"
    min_confidence_pct: int = Field(default=50, ge=0, le=100)
    min_frp_mw: float = Field(default=0.0, ge=0.0)
    # A single detection is not an event: require a cluster before an AOI
    # is triggered or its post-fire window is opened.
    min_hotspots: int = Field(default=2, ge=1)
    trigger_window_hours: int = Field(default=24, ge=1)
    # Skip AOIs whose latest assessment is fresher than this.
    cooldown_minutes: int = Field(default=90, ge=0)
    # National bbox (west, south, east, north) — one transaction per source.
    bbox: tuple[float, float, float, float] = (6.0, 35.0, 19.0, 48.0)

    @property
    def active(self) -> bool:
        """Feed is usable: switched on *and* a MAP_KEY is present."""
        return self.enabled and self.map_key is not None


class ReportSettings(BaseSettings):
    """Daily national report dispatched on the notification channels."""

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    # UTC hour of the daily dispatch (07:00 Europe/Rome in winter = 06 UTC).
    hour_utc: int = Field(default=6, ge=0, le=23)

    # --- Report HTML statico (job limen-html-report) ---
    html_enabled: bool = True
    html_interval_hours: int = Field(default=1, ge=1)
    html_run_at_startup: bool = True
    html_output_dir: Path = Path("site")
    html_max_clusters: int = Field(default=50, ge=1)
    html_min_level: RiskLevel = RiskLevel.High
    html_cluster_eps_deg: float = Field(default=0.02, gt=0)
    # Salienza: quando un AOI ha più di *trigger* celle a rischio, invece di
    # clusterizzare l'intera macchia (mezza regione a Moderate) si evidenziano
    # solo le celle che spiccano sullo sfondo: score >= percentile(ref) + margin.
    # Il resto ("coda lunga") è riportato come conteggio, mai scartato in silenzio.
    html_salience_volume_trigger: int = Field(default=200, ge=1)
    html_salience_reference_pct: float = Field(default=0.5, ge=0.0, le=1.0)
    html_salience_min_anomaly: float = Field(default=0.08, ge=0.0)
    html_archive_keep: int = Field(default=240, ge=1)
    html_basemap_url_template: str = "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
    html_basemap_attribution: str = "© OpenStreetMap contributors © CARTO"
    html_publish: bool = False


class VerifySettings(BaseSettings):
    """Fact-checking of archived report zones vs real events (#17)."""

    model_config = SettingsConfigDict(extra="ignore")

    # Match radius from a zone's cells (m), computed in EPSG:3035. ~grid scale.
    match_radius_m: float = Field(default=2000.0, gt=0.0)
    # Window after valuation_time in which an event counts as triggered.
    horizon_hours: int = Field(default=72, ge=1)
    # Extra wait before a build is verifiable (late-arriving events).
    grace_hours: int = Field(default=24, ge=0)


class ContributiSettings(BaseSettings):
    """I contributi degli esperti dall'ispettore della cella.

    Partono per mail con il server SMTP di ``NOTIFICATIONS__EMAIL`` ma verso
    destinatari propri: chi cura il progetto non è il centro operativo che
    riceve le allerte. Non si salvano: senza destinatari o senza SMTP il
    modulo risponde che il contributo non è partito.
    """

    model_config = SettingsConfigDict(extra="ignore")

    destinatari: list[str] = Field(default_factory=list)
    max_per_ip_ora: int = Field(default=3, ge=1)
    # Un tetto complessivo, perché un indirizzo IP si cambia e la casella che
    # riceve è di una persona.
    max_totali_ora: int = Field(default=30, ge=1)
    # Sotto questo tempo di compilazione il modulo l'ha riempito un programma.
    secondi_minimi: float = Field(default=5.0, ge=0.0)


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
    contributi: ContributiSettings = Field(default_factory=ContributiSettings)
    alert: AlertSettings = Field(default_factory=AlertSettings)
    forecast: ForecastSettings = Field(default_factory=ForecastSettings)
    report: ReportSettings = Field(default_factory=ReportSettings)
    verify: VerifySettings = Field(default_factory=VerifySettings)
    nowcast: NowcastSettings = Field(default_factory=NowcastSettings)
    firms: FirmsSettings = Field(default_factory=FirmsSettings)
    iot: IotSettings = Field(default_factory=IotSettings)
    hazards: HazardsSettings = Field(default_factory=HazardsSettings)
    scoring: ScoringSettings = Field(default_factory=ScoringSettings)
    training: TrainingSettings = Field(default_factory=TrainingSettings)
    egms: EgmsSettings = Field(default_factory=EgmsSettings)
    copernicus: CopernicusSettings = Field(default_factory=CopernicusSettings)
    radar_archive: RadarArchiveSettings = Field(default_factory=RadarArchiveSettings)
    backup: BackupSettings = Field(default_factory=BackupSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    openmeteo: OpenMeteoSettings = Field(default_factory=OpenMeteoSettings)
    kg: KgSettings = Field(default_factory=KgSettings)
    geodata: GeodataSettings = Field(default_factory=GeodataSettings)
    geoserver_source: GeoServerSourceSettings = Field(default_factory=GeoServerSourceSettings)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = False

    # Workflow toggles
    # `enable_insitu` gates the conditional IoT (sensor_fetch) edge in the
    # MAF workflow. V1 default = False (no IoT). V1.5 will flip this when
    # the real sensor ingestion lands.
    enable_insitu: bool = False
    # Issue #8: dynamic flood feed (forecast rain + GloFAS river discharge +
    # marine surge), scaled by the ISPRA hydraulic hazard. ON by default — flood
    # risk is a first-class output alongside landslides. Each signal degrades to
    # None where not applicable (inland ⇒ no marine, off-reach ⇒ no discharge),
    # so the assessment stays correct. Set False to disable the extra fetches.
    # NOT the flood hazard. This gates the dynamic hydrology signals that feed
    # component H of *landslide* scoring (issue #8). The flood hazard is a
    # separate engine selected through HAZARDS__ENABLED (Fase 3, issue #63).
    enable_flood_forecast: bool = True
    # Rainfall sampling-node grid step (degrees) for the live MeteoFetch —
    # each cell gets the series of its nearest node instead of one AOI-wide
    # centroid series. 0 disables the grid (centroid-only).
    meteo_rain_node_deg: float = Field(default=0.25, ge=0.0)

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
