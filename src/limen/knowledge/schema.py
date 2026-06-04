"""Pydantic payloads exchanged with the KG sidecar.

The sidecar exposes a small JSON-over-HTTP surface:

* ``POST /ingest`` — push one or more documents with a stable
  ``thread_id``. Idempotency is the sidecar's responsibility; we still
  hash payloads upstream so re-runs are cheap.
* ``POST /query``  — hybrid Graph-RAG retrieval. Returns a ranked list
  of passages each carrying a citation.

The shapes here are intentionally narrow — anything Limen doesn't
consume stays out of the schema so a sidecar API tweak doesn't
ripple here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IngestDocument(BaseModel):
    """One document pushed to the KG sidecar."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(..., min_length=1)
    """Stable identifier (URI, DOI, file path). The sidecar uses it as
    the natural key — re-ingesting the same ``source`` updates the
    upstream document in place."""
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    """Plain-text body. PDFs / scans MUST be OCR'd upstream."""
    kind: Literal["paper", "pai_plan", "ispra_report", "iffi_event", "limen_briefing"]
    metadata: dict[str, str] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    """One ``POST /ingest`` call payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    thread_id: str
    ontology_version: str | None = None
    documents: tuple[IngestDocument, ...]


class GroundingQuery(BaseModel):
    """Inputs for the advisory grounding lookup.

    The fields mirror the *driver context* the BriefingAgent assembles
    from the deterministic engine's output — no LLM, no I/O, no risk
    of the query depending on a network state.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    region: str
    """Italian region or macro-area covering the AOI (e.g. ``Puglia``)."""
    mechanism: Literal[
        "static_susceptibility",
        "meteo_trigger",
        "seismic_event",
        "post_fire_destabilization",
        "human_activity",
    ]
    """The driver chosen by the RiskAnalyst — also the cache key axis."""
    top_k: int = Field(default=4, ge=1, le=20)


class Passage(BaseModel):
    """One ranked passage returned by ``POST /query``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    title: str
    snippet: str
    citation: str
    score: float = Field(..., ge=0.0, le=1.0)


class GroundingResult(BaseModel):
    """``POST /query`` response, narrowed to what Limen surfaces."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: GroundingQuery
    passages: tuple[Passage, ...]

    @property
    def is_empty(self) -> bool:
        return not self.passages


__all__ = [
    "GroundingQuery",
    "GroundingResult",
    "IngestDocument",
    "IngestRequest",
    "Passage",
]
