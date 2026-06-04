"""Landslide-domain ontology (project doc §2.8).

The same `entity → relation → entity` graph the team's `knowledge-graph`
project is configured to extract. This file is the *single source of
truth*; the ingestion job ships a normalised copy of :data:`ONTOLOGY`
to the KG sidecar so extraction stays aligned with what Limen later
queries.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Entity:
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class Relation:
    name: str
    head: str
    tail: str
    description: str


ENTITIES: tuple[Entity, ...] = (
    Entity("Paper", "Scientific paper or technical report about landslides."),
    Entity("Author", "Author of a Paper."),
    Entity(
        "RainfallThreshold",
        "Rainfall-intensity-duration threshold (Caine-style) above which "
        "shallow landslide triggering becomes likely.",
    ),
    Entity(
        "TriggerMechanism",
        "Physical mechanism driving slope failure (e.g. rainfall, seismic, "
        "post-fire destabilisation, anthropic).",
    ),
    Entity(
        "LandslideType",
        "Movement type per Cruden & Varnes (slide, flow, fall, topple, complex).",
    ),
    Entity("Lithology", "Rock/soil type relevant to slope stability."),
    Entity("Region", "Italian region or macro-area (Puglia, Basilicata, Apennines, ...)."),
    Entity("Area", "Sub-regional area (province, municipality, watershed)."),
    Entity("HistoricalEvent", "Documented past landslide event."),
    Entity(
        "NormativePlan",
        "Regulatory plan referencing landslide hazard (PAI, PAI Aggiornato, "
        "Piano di Assetto Idrogeologico).",
    ),
)

RELATIONS: tuple[Relation, ...] = (
    Relation(
        "DEFINES_THRESHOLD",
        "Paper",
        "RainfallThreshold",
        "A paper publishes / calibrates a rainfall threshold.",
    ),
    Relation(
        "VALID_FOR_REGION",
        "RainfallThreshold",
        "Region",
        "Threshold's applicable geographic scope.",
    ),
    Relation(
        "TRIGGERED_BY",
        "HistoricalEvent",
        "TriggerMechanism",
        "Past event attributed to a given triggering mechanism.",
    ),
    Relation(
        "DOCUMENTED_IN",
        "HistoricalEvent",
        "Paper",
        "Event documented in a paper / report.",
    ),
    Relation(
        "OCCURRED_IN",
        "HistoricalEvent",
        "Area",
        "Spatial extent of an event.",
    ),
    Relation(
        "SUPPORTS_PARAMETER",
        "Paper",
        "RainfallThreshold",
        "Empirical / theoretical support cited for a parameter.",
    ),
)


@dataclass(frozen=True, slots=True)
class Ontology:
    """Bundle of entities + relations + a stable version tag."""

    version: str
    entities: tuple[Entity, ...]
    relations: tuple[Relation, ...]

    def to_kg_payload(self) -> dict[str, object]:
        """JSON shape consumed by the KG sidecar at configuration time."""
        return {
            "version": self.version,
            "entities": [{"name": e.name, "description": e.description} for e in self.entities],
            "relations": [
                {
                    "name": r.name,
                    "head": r.head,
                    "tail": r.tail,
                    "description": r.description,
                }
                for r in self.relations
            ],
        }


ONTOLOGY: Ontology = Ontology(
    version="2026-06-04",
    entities=ENTITIES,
    relations=RELATIONS,
)


__all__ = ["ENTITIES", "ONTOLOGY", "RELATIONS", "Entity", "Ontology", "Relation"]
