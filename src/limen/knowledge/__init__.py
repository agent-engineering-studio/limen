"""Knowledge-graph grounding (V2.x).

Public surface:

* :class:`Entity` / :class:`Relation` / :data:`ONTOLOGY` — the
  landslide-domain schema the KG sidecar is configured with.
* :class:`IngestDocument` / :class:`IngestRequest` — payloads sent to
  the sidecar's ``POST /ingest`` endpoint.
* :class:`GroundingQuery` / :class:`Passage` / :class:`GroundingResult`
  — payloads consumed from the sidecar's ``POST /query`` endpoint.

The KG is **advisory only** — every consumer (BriefingAgent, ingestion
CLI) must degrade gracefully when the sidecar is unreachable. None of
this code path is permitted to alter numeric scoring outputs.
"""

from limen.knowledge.ontology import ONTOLOGY, Entity, Relation
from limen.knowledge.schema import (
    GroundingQuery,
    GroundingResult,
    IngestDocument,
    IngestRequest,
    Passage,
)

__all__ = [
    "ONTOLOGY",
    "Entity",
    "GroundingQuery",
    "GroundingResult",
    "IngestDocument",
    "IngestRequest",
    "Passage",
    "Relation",
]
