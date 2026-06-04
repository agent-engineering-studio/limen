"""Offline corpus ingestion to the knowledge-graph sidecar.

The job walks a corpus directory and POSTs each readable document to
``{KG__BASE_URL}/ingest`` under the configured ``thread_id``. Each call
ships the current ontology version so the sidecar can re-extract if it
has changed.

Idempotency is layered:

* The sidecar dedupes by ``source`` (per Limen-doc §3.14).
* Limen registers a content hash in :sql:`dataset_versions` so a
  re-run that hashes identically is a no-op locally.

Network failures degrade to a warning + zero documents processed —
ingestion is best-effort and never runs in the hourly critical path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
import structlog

from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.data.repos.dataset_versions_repo import content_hash
from limen.integrations._http import SharedHttpClient
from limen.knowledge.ontology import ONTOLOGY
from limen.knowledge.schema import IngestDocument, IngestRequest

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


_KIND_BY_SUFFIX: dict[
    str, Literal["paper", "pai_plan", "ispra_report", "iffi_event", "limen_briefing"]
] = {
    ".paper.md": "paper",
    ".paper.txt": "paper",
    ".pai.md": "pai_plan",
    ".ispra.md": "ispra_report",
    ".iffi.md": "iffi_event",
    ".briefing.md": "limen_briefing",
}


@dataclass(frozen=True, slots=True)
class IngestResult:
    documents_seen: int
    documents_sent: int
    skipped_unchanged: bool


def discover_documents(root: Path) -> list[IngestDocument]:
    """Walk ``root`` and build typed documents from the recognised suffixes.

    Suffix → kind mapping (preserves Limen-doc §3.14 categories):
    ``*.paper.{md,txt}`` → ``paper``,
    ``*.pai.md`` → ``pai_plan``,
    ``*.ispra.md`` → ``ispra_report``,
    ``*.iffi.md`` → ``iffi_event``,
    ``*.briefing.md`` → ``limen_briefing``.

    Unknown suffixes are skipped (logged at debug). The first non-empty
    line of each file is taken as the title — keeps the contract narrow
    enough for non-Markdown sources.
    """
    if not root.exists():
        return []
    out: list[IngestDocument] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        kind = _match_suffix(path)
        if kind is None:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            _log.warning("kg.ingest.read_skip", path=str(path), error=str(exc))
            continue
        if not content.strip():
            continue
        title = _extract_title(content) or path.stem
        out.append(
            IngestDocument(
                source=str(path),
                title=title,
                content=content,
                kind=kind,
                metadata={
                    "ingested_at": datetime.now(UTC).isoformat(),
                    "filename": path.name,
                },
            )
        )
    return out


def _match_suffix(
    path: Path,
) -> Literal["paper", "pai_plan", "ispra_report", "iffi_event", "limen_briefing"] | None:
    name = path.name.lower()
    for suffix, kind in _KIND_BY_SUFFIX.items():
        if name.endswith(suffix):
            return kind
    return None


def _extract_title(content: str) -> str | None:
    for raw_line in content.splitlines():
        line = raw_line.strip().lstrip("#").strip()
        if line:
            return line[:240]
    return None


async def _send_request(
    *,
    base_url: str,
    timeout_seconds: float,
    api_token: str | None,
    request: IngestRequest,
) -> bool:
    headers: dict[str, str] = {"content-type": "application/json"}
    if api_token:
        headers["authorization"] = f"Bearer {api_token}"
    url = f"{base_url.rstrip('/')}/ingest"
    payload = json.dumps(request.model_dump(mode="json"))
    client = await SharedHttpClient.get()
    try:
        response = await client.post(url, headers=headers, content=payload, timeout=timeout_seconds)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        _log.warning(
            "kg.ingest.http_error",
            error=str(exc),
            error_type=type(exc).__name__,
            url=url,
        )
        return False
    except Exception as exc:
        _log.warning(
            "kg.ingest.unexpected_error",
            error=str(exc),
            error_type=type(exc).__name__,
            url=url,
        )
        return False
    return True


async def _register_dataset_version(*, source: str, dataset: str, version: str) -> None:
    """Stamp the (source, dataset, version) tuple so re-runs detect a no-op."""
    from limen.data.db import acquire

    async with acquire() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO dataset_versions (source, dataset, version, fetched_at, metadata)
                VALUES ($1, $2, $3, now(), '{}'::jsonb)
                ON CONFLICT (source, dataset, version) DO UPDATE
                SET fetched_at = EXCLUDED.fetched_at
                """,
                source,
                dataset,
                version,
            )
        except Exception as exc:  # bookkeeping never blocks ingestion
            _log.warning("kg.ingest.dataset_version.skip", error=str(exc))


async def _dataset_version_exists(*, source: str, dataset: str, version: str) -> bool:
    from limen.data.db import acquire

    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 1 FROM dataset_versions
            WHERE source = $1 AND dataset = $2 AND version = $3
            """,
            source,
            dataset,
            version,
        )
    return row is not None


async def ingest_corpus(
    *,
    corpus_root: Path,
    settings: Settings | None = None,
    skip_dataset_version_check: bool = False,
) -> IngestResult:
    """Walk ``corpus_root`` and push documents to the KG sidecar.

    Returns counts so the CLI can render a meaningful summary. The
    operation is allowed to fail silently — caller code should not
    treat ``documents_sent == 0`` as an error.
    """
    s = settings or get_settings()
    documents = discover_documents(corpus_root)
    if not documents:
        _log.info("kg.ingest.empty", root=str(corpus_root))
        return IngestResult(documents_seen=0, documents_sent=0, skipped_unchanged=False)

    if not s.kg.enabled:
        _log.info(
            "kg.ingest.skip_disabled",
            hint="set KG__ENABLED=true to push to the sidecar",
            documents_seen=len(documents),
        )
        return IngestResult(
            documents_seen=len(documents), documents_sent=0, skipped_unchanged=False
        )

    payload_hash = content_hash(
        json.dumps(
            [d.model_dump(mode="json") for d in documents],
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    )

    if not skip_dataset_version_check:
        unchanged = await _dataset_version_exists(
            source="limen.knowledge",
            dataset=s.kg.thread_id,
            version=payload_hash,
        )
        if unchanged:
            _log.info(
                "kg.ingest.skip_unchanged",
                thread_id=s.kg.thread_id,
                content_hash=payload_hash[:12],
                documents_seen=len(documents),
            )
            return IngestResult(
                documents_seen=len(documents),
                documents_sent=0,
                skipped_unchanged=True,
            )

    request = IngestRequest(
        thread_id=s.kg.thread_id,
        ontology_version=ONTOLOGY.version,
        documents=tuple(documents),
    )
    api_token = s.kg.api_token.get_secret_value() if s.kg.api_token is not None else None
    success = await _send_request(
        base_url=s.kg.base_url,
        timeout_seconds=s.kg.timeout_seconds * 10.0,  # ingestion is offline, larger budget
        api_token=api_token,
        request=request,
    )
    if not success:
        return IngestResult(
            documents_seen=len(documents),
            documents_sent=0,
            skipped_unchanged=False,
        )

    await _register_dataset_version(
        source="limen.knowledge",
        dataset=s.kg.thread_id,
        version=payload_hash,
    )
    _log.info(
        "kg.ingest.done",
        thread_id=s.kg.thread_id,
        documents_sent=len(documents),
        content_hash=payload_hash[:12],
    )
    return IngestResult(
        documents_seen=len(documents),
        documents_sent=len(documents),
        skipped_unchanged=False,
    )


__all__ = ["IngestResult", "discover_documents", "ingest_corpus"]
