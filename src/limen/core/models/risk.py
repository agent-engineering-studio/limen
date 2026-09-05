"""Risk-domain DTOs.

These are the *only* types the deterministic engine reads from and
writes to. They are intentionally side-effect-free Pydantic v2 models
so:

* the engine stays a pure function of its inputs;
* assembling the bundle (DB queries, Open-Meteo / INGV / EFFIS fetches)
  is a separate concern that can be tested independently in Phase 4;
* the V2 ML engine can be a drop-in by consuming the same
  ``CellFeatureBundle``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Generic, Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from limen.core.models.hazard import HazardType
from limen.core.models.sensor import SensorFeatures


class RiskLevel(StrEnum):
    """Five-class classification used by the V1 engine.

    Member names follow the project spec: ``None_`` (Python's ``None``
    is a reserved keyword, so a trailing underscore), ``Low``,
    ``Moderate``, ``High``, ``VeryHigh``. Values are the human-readable
    forms used in API responses and JSON dumps.
    """

    None_ = "None"
    Low = "Low"
    Moderate = "Moderate"
    High = "High"
    VeryHigh = "VeryHigh"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
class StaticFactors(_Frozen):
    """Per-cell static factors (mirror of ``cell_static_factors`` columns).

    Every field is optional: when the underlying source isn't yet
    populated (DEM / CORINE / lithology pipelines land later), the
    engine must degrade — not crash.
    """

    cell_id: str
    susc_ispra: float | None = Field(default=None, ge=0.0, le=1.0)
    iffi_density_500: float | None = Field(default=None, ge=0.0)
    distance_to_iffi_m: float | None = Field(default=None, ge=0.0)
    slope_deg: float | None = Field(default=None, ge=0.0, le=90.0)
    aspect_deg: float | None = Field(default=None, ge=0.0, le=360.0)
    elevation_m: float | None = None
    twi: float | None = None
    curvature: float | None = None
    lithology: str | None = None
    litho_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    landuse_code: str | None = None
    pai_class_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    # Phase 12+ — ISPRA Mosaicatura Idraulica, mapped onto the same
    # AA/P1..P4 ladder as PAI. NULL = unknown; the landslide engine treats
    # unknown as H = 0, the flood engine as its `susceptibility.unmapped`
    # floor -- "not studied" is not "not floodable".
    flood_hazard_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    # Fase 3a (#63) — CLMS Imperviousness Density, frazione di suolo
    # impermeabilizzato. Amplifica il solo ramo pluviale: il cemento non fa
    # crescere un fiume, fa scorrere la stessa pioggia invece di lasciarla
    # infiltrare. NULL = ignoto, che non è 0 (= suolo tutto permeabile).
    imperviousness_norm: float | None = Field(default=None, ge=0.0, le=1.0)


class RainfallSample(_Frozen):
    """One hourly rainfall observation (mm)."""

    timestamp: datetime
    precipitation_mm: float = Field(..., ge=0.0)


class RainfallSeries(_Frozen):
    """Hourly precipitation time-series used by Caine + API computations."""

    samples: tuple[RainfallSample, ...] = ()

    @property
    def total_mm(self) -> float:
        return float(sum(s.precipitation_mm for s in self.samples))


class SeismicHistoryEvent(_Frozen):
    """One past seismic event relevant to a cell (within the lookback window)."""

    event_id: str
    origin_time: datetime
    magnitude: float = Field(..., gt=0.0)
    distance_km: float = Field(..., ge=0.0)
    pga_g: float = Field(..., ge=0.0, description="Local PGA in units of g")


class DynamicInputs(_Frozen):
    """Time-varying inputs needed by M / E / F components."""

    valuation_time: datetime
    rainfall: RainfallSeries = RainfallSeries()
    api_30_mm: float | None = Field(default=None, ge=0.0)
    api_baseline_mm: float | None = Field(default=None, ge=0.0)
    soil_moisture_0_7: float | None = Field(default=None, ge=0.0, le=1.0)
    # Standing snowpack depth over the window (m) — drives the rain-on-snow
    # amplification of M. AOI-level in V1 (like soil moisture).
    snow_depth_m: float | None = Field(default=None, ge=0.0)
    # Issue #8 — dynamic flood signals (opt-in feed). All None ⇒ flood bonus 0.
    # pluvial: forecast cumulated rain over the next 72 h (mm).
    flood_forecast_rain_72h_mm: float | None = Field(default=None, ge=0.0)
    # fluvial: forecast peak river discharge / seasonal normal (Open-Meteo Flood).
    river_discharge_ratio: float | None = Field(default=None, ge=0.0)
    # coastal: normalised sea surge / wave signal in [0,1] (Open-Meteo Marine).
    coastal_surge_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    seismic_history: tuple[SeismicHistoryEvent, ...] = ()
    months_since_fire: float | None = Field(default=None, ge=0.0)
    # Fase 2a (#61) — i sei numeri della catena FWI per questa cella, già
    # avanzati al giorno di valutazione dallo step FwiUpdate. Assente sulle
    # celle senza stato ricorsivo: il motore incendio lo dichiara invece di
    # inventare un indice da uno stato che non c'è.
    fire_weather: FireWeatherState | None = None
    # V1.5 — per-cell in-situ aggregate. Absent on cells without sensors;
    # the engine then runs the pure V1 path for that cell.
    sensor_features: SensorFeatures | None = None


class CellFeatureBundle(_Frozen):
    """Engine input — everything needed to score one cell at one moment."""

    aoi_id: str
    cell_id: str
    static: StaticFactors
    dynamic: DynamicInputs
    macroregion: str = "italy_default"

    @model_validator(mode="after")
    def _cell_id_consistency(self) -> CellFeatureBundle:
        if self.static.cell_id != self.cell_id:
            raise ValueError(
                f"CellFeatureBundle.cell_id ({self.cell_id!r}) "
                f"differs from static.cell_id ({self.static.cell_id!r})"
            )
        return self


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
class StaticBreakdown(_Frozen):
    susc_ispra: float = Field(..., ge=0.0, le=1.0)
    iffi_density: float = Field(..., ge=0.0, le=1.0)
    slope: float = Field(..., ge=0.0, le=1.0)
    pai: float = Field(..., ge=0.0, le=1.0)
    litho_weight: float = Field(..., ge=0.0, le=1.0)


class MeteoBreakdown(_Frozen):
    caine_excess: float = Field(..., ge=0.0)
    caine_norm: float = Field(..., ge=0.0, le=1.0)
    api_factor: float = Field(..., ge=0.0, le=1.0)
    soil_factor: float = Field(..., ge=0.0, le=1.0)
    # Rain-on-snow amplification (0 when no snowpack / no snow block).
    snow_factor: float = Field(default=0.0, ge=0.0, le=1.0)
    # V1.5: which inputs came from in-situ sensors (vs Open-Meteo).
    # Empty tuple on the pure V1 path.
    measured_overrides: tuple[str, ...] = ()


class KinematicBreakdown(_Frozen):
    """Sub-terms for the V1.5 K component (zero when no sensor coverage)."""

    velocity_mmd: float | None = None
    acceleration_mmd2: float | None = None
    inverse_velocity: float | None = None
    velocity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    acceleration_score: float = Field(default=0.0, ge=0.0, le=1.0)
    hard_escalation: bool = False


class FireWeatherState(_Frozen):
    """La catena FWI di una cella in un giorno (Van Wagner 1987).

    Input del motore incendio, non output: i tre codici ricorsivi vivono in
    `fwi_state` e attraversano i riavvii, e questa è la loro lettura del
    giorno insieme ai tre indici derivati.
    """

    day: date
    ffmc: float = Field(..., ge=0.0, le=101.0)
    dmc: float = Field(..., ge=0.0)
    dc: float = Field(..., ge=0.0)
    isi: float = Field(..., ge=0.0)
    bui: float = Field(..., ge=0.0)
    fwi: float = Field(..., ge=0.0)
    #: Giorni consecutivi di catena alle spalle. Sotto lo spin-up i codici
    #: non sono ancora significativi e il motore lo segnala.
    chain_days: int = Field(default=0, ge=0)


class HazardBreakdown(_Frozen):
    """Base of every per-hazard breakdown.

    Carries the discriminator plus three **projections**. Component *names*
    are hazard-specific by definition -- S/M/E/F/H/K describe how a slope
    fails and mean nothing for a wildfire -- so the base holds no components
    of its own; instead it declares the three questions every consumer that
    must work for any hazard actually asks. Each subclass answers them in its
    own terms, and no consumer grows a branch per danger.
    """

    hazard_type: HazardType

    def components(self) -> dict[str, float]:
        """Named drivers, for a narrative or a generic breakdown view.

        Labels are the hazard's own: the briefing quotes the top three and
        must not have to know which danger it is describing.
        """
        return {}

    def factors_payload(self) -> dict[str, Any]:
        """What goes into ``risk_assessments.factors``.

        Owned here rather than by the persistence executor so the stored
        shape follows the breakdown that produced it. The landslide payload
        is byte-identical to the one written before this method existed --
        rows and the ``/api/cell/{id}/breakdown`` reader are untouched.
        """
        return self.model_dump(mode="json")

    def predisposition(self) -> float:
        """Static susceptibility in [0, 1] -- terrain, not weather.

        The alert gate uses it to keep below-High alerts to cells that are
        actually predisposed ("moderate rain on a susceptible slope", not
        "moderate rain anywhere"). Every hazard has such a notion; which
        component carries it is the subclass's business.
        """
        return 0.0

    @classmethod
    def from_factors(cls, payload: dict[str, Any]) -> Self:
        """Rebuild from a persisted ``factors`` blob.

        The inverse of :meth:`factors_payload`. It exists as a method, not as
        a plain ``model_validate`` at the call site, because JSONB does not
        round-trip Python types: these models are ``strict=True``, so a date
        comes back as a string and is refused. Each subclass restores what its
        own payload lost.
        """
        discriminator = cls.model_fields["hazard_type"].default
        return cls.model_validate({**payload, "hazard_type": discriminator})


class ComponentBreakdown(HazardBreakdown):
    """Landslide components + their normalised inputs, for auditability.

    V1 ships five components (S/M/E/F/H, ``k`` always 0). V1.5 activates
    K on monitored cells and renormalises the others — but the same DTO
    shape carries both regimes so downstream consumers (ChatAgents,
    persistence, frontend) stay backwards-compatible.

    The name is kept from before the hazard dimension existed: renaming it
    would touch every scoring consumer for no gain. Fase 2 adds
    ``FloodBreakdown`` and ``WildfireBreakdown`` alongside it.
    """

    hazard_type: Literal[HazardType.LANDSLIDE] = HazardType.LANDSLIDE

    s: float = Field(..., ge=0.0, le=1.0)
    m: float = Field(..., ge=0.0, le=1.0)
    e: float = Field(..., ge=0.0, le=1.0)
    f: float = Field(..., ge=0.0, le=1.0)
    h: float = Field(..., ge=0.0, le=1.0)
    k: float = Field(default=0.0, ge=0.0, le=1.0)

    static_terms: StaticBreakdown
    meteo_terms: MeteoBreakdown
    kinematic_terms: KinematicBreakdown | None = None

    def components(self) -> dict[str, float]:
        return {"S": self.s, "M": self.m, "E": self.e, "F": self.f, "H": self.h, "K": self.k}

    def factors_payload(self) -> dict[str, Any]:
        # Exactly the keys `PersistResultExecutor` wrote before the projection
        # existed: changing them would silently reshape every stored row and
        # break the breakdown endpoint's reader.
        return {
            "s": self.s,
            "m": self.m,
            "e": self.e,
            "f": self.f,
            "h": self.h,
            "static_terms": self.static_terms.model_dump(),
            "meteo_terms": self.meteo_terms.model_dump(),
        }

    def predisposition(self) -> float:
        return self.s


class WildfireBreakdown(HazardBreakdown):
    """Componenti del pericolo incendio (#61).

    Nessuna sovrapposizione con `ComponentBreakdown`: `fwi` è meteo del
    giorno, `fuel` è copertura del suolo, `slope` è morfologia. Chiamarli
    S/M/E sarebbe una coincidenza di lettere, non di significato.
    """

    hazard_type: Literal[HazardType.WILDFIRE] = HazardType.WILDFIRE

    fwi_norm: float = Field(..., ge=0.0, le=1.0)
    fuel: float = Field(..., ge=0.0, le=1.0)
    slope: float = Field(..., ge=0.0, le=1.0)

    #: La catena grezza, per verificabilità: un operatore che contesta un
    #: punteggio deve poter risalire ai sei numeri di Van Wagner.
    fire_weather: FireWeatherState | None = None
    #: Vero quando la catena non ha ancora abbastanza giorni alle spalle,
    #: o non c'è affatto. Il punteggio esiste comunque, ma va letto sapendolo.
    spinup: bool = False

    def components(self) -> dict[str, float]:
        return {"FWI": self.fwi_norm, "Combustibile": self.fuel, "Pendenza": self.slope}

    def factors_payload(self) -> dict[str, Any]:
        return {
            "fwi_norm": self.fwi_norm,
            "fuel": self.fuel,
            "slope": self.slope,
            "spinup": self.spinup,
            "fire_weather": (
                self.fire_weather.model_dump(mode="json") if self.fire_weather is not None else None
            ),
        }

    def predisposition(self) -> float:
        # Il combustibile è ciò che una cella *è*, indipendentemente dal
        # tempo del giorno: è l'analogo della suscettibilità di un versante.
        return self.fuel

    @classmethod
    def from_factors(cls, payload: dict[str, Any]) -> Self:
        # `day` torna da JSONB come stringa, e il modello è strict: senza
        # questa conversione ogni riga incendio farebbe 500 sulla lettura.
        raw = dict(payload)
        fw = raw.get("fire_weather")
        if isinstance(fw, dict) and isinstance(fw.get("day"), str):
            fw = {**fw, "day": date.fromisoformat(fw["day"])}
            raw["fire_weather"] = fw
        return super().from_factors(raw)


class FloodBreakdown(HazardBreakdown):
    """Componenti del pericolo alluvione (#63).

    `susceptibility` è ciò che la cella *è* — dal mosaico idraulico ISPRA —
    e i due trigger sono i due modi in cui l'acqua ci arriva. Tenuti
    distinti, non sommati: sono mitigati da cose diverse, e un operatore
    deve sapere quale dei due sta guardando.
    """

    hazard_type: Literal[HazardType.FLOOD] = HazardType.FLOOD

    susceptibility: float = Field(..., ge=0.0, le=1.0)
    pluvial: float = Field(..., ge=0.0, le=1.0)
    fluvial: float = Field(..., ge=0.0, le=1.0)

    #: Falso quando la cella è fuori dalle zone mappate e la suscettibilità
    #: è il valore di ripiego: il punteggio esiste ma poggia su meno.
    mapped: bool = True
    #: I segnali grezzi, per verificabilità.
    discharge_ratio: float | None = None
    rain_mm: float | None = None

    def components(self) -> dict[str, float]:
        return {
            "Suscettibilità": self.susceptibility,
            "Pioggia": self.pluvial,
            "Fiume": self.fluvial,
        }

    def factors_payload(self) -> dict[str, Any]:
        return {
            "susceptibility": self.susceptibility,
            "pluvial": self.pluvial,
            "fluvial": self.fluvial,
            "mapped": self.mapped,
            "discharge_ratio": self.discharge_ratio,
            "rain_mm": self.rain_mm,
        }

    def predisposition(self) -> float:
        # La suscettibilità idraulica è ciò che la cella è a prescindere dal
        # tempo: l'analogo della fragilità di un versante.
        return self.susceptibility


#: The concrete breakdowns, discriminated by ``hazard_type``. Pydantic needs
#: the closed union to round-trip a nested breakdown; the base class alone
#: would serialise only the discriminator and drop every number.
AnyHazardBreakdown = Annotated[
    ComponentBreakdown | WildfireBreakdown | FloodBreakdown,
    Field(discriminator="hazard_type"),
]

_BREAKDOWN_BY_HAZARD: dict[HazardType, type[HazardBreakdown]] = {
    HazardType.LANDSLIDE: ComponentBreakdown,
    HazardType.WILDFIRE: WildfireBreakdown,
    HazardType.FLOOD: FloodBreakdown,
}


def breakdown_from_factors(hazard: HazardType, payload: dict[str, Any]) -> HazardBreakdown:
    """Rebuild a breakdown from a persisted ``factors`` blob.

    Dispatches to the hazard's own :meth:`HazardBreakdown.from_factors`, which
    restores whatever JSONB flattened. Callers that read historical rows are
    responsible for supplying defaults for keys a newer pipeline added --
    :mod:`limen.api.endpoints.risk` does that for landslide.
    """
    cls = _BREAKDOWN_BY_HAZARD.get(hazard)
    if cls is None:
        raise ValueError(f"no breakdown class for hazard {hazard.value!r}")
    return cls.from_factors(payload)


#: Covariant because :class:`RiskScore` is frozen: a
#: ``RiskScore[ComponentBreakdown]`` is safely usable wherever a
#: ``RiskScore[HazardBreakdown]`` is expected, which is what lets the engine
#: registry hold engines for different hazards behind one type.
BreakdownT_co = TypeVar("BreakdownT_co", bound=HazardBreakdown, covariant=True)


# UP046 is suppressed below: PEP 695 (`class RiskScore[B: HazardBreakdown]`)
# infers variance instead of declaring it, and mypy infers *invariant* here
# because a Pydantic field reads as a mutable attribute. That breaks the
# assignment this design depends on, RiskScore[ComponentBreakdown] into
# RiskScore[HazardBreakdown], so the explicit covariant TypeVar has to stay.
class RiskScore(_Frozen, Generic[BreakdownT_co]):  # noqa: UP046
    """Engine output, parameterised by the hazard's breakdown shape.

    Generic rather than pinned to :class:`ComponentBreakdown` so the
    landslide engine can return ``RiskScore[ComponentBreakdown]`` and its
    callers keep reading ``.breakdown.s`` with no cast and no narrowing,
    while a flood or wildfire engine returns its own breakdown through the
    same class.
    """

    score: float = Field(..., ge=0.0, le=1.0)
    level: RiskLevel
    breakdown: BreakdownT_co
    model_version: str
    # V1.5 — operator-facing hint that the engine took the in-situ path
    # for this cell (raised confidence + the M' override + K active).
    monitored: bool = False
    # V1.5 — set by the engine when acceleration ≥ alarm. The
    # AlertDispatch executor uses this to bypass the threshold gate.
    hard_escalation: bool = False

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


__all__: Sequence[str] = (
    "AnyHazardBreakdown",
    "BreakdownT_co",
    "CellFeatureBundle",
    "ComponentBreakdown",
    "DynamicInputs",
    "FireWeatherState",
    "FloodBreakdown",
    "HazardBreakdown",
    "KinematicBreakdown",
    "MeteoBreakdown",
    "RainfallSample",
    "RainfallSeries",
    "RiskLevel",
    "RiskScore",
    "SeismicHistoryEvent",
    "SensorFeatures",
    "StaticBreakdown",
    "StaticFactors",
    "WildfireBreakdown",
    "breakdown_from_factors",
)
