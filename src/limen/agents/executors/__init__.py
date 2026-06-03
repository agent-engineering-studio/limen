"""Custom workflow executors.

Each executor is a thin :class:`Executor` subclass that reads/writes
parts of :class:`MonitoringContext`. None of them computes risk
themselves — that's the deterministic scoring engine's job, called
from :class:`RiskScoring`.
"""

from limen.agents.executors.alert_dispatch import AlertDispatchExecutor
from limen.agents.executors.area_resolver import AreaResolverExecutor
from limen.agents.executors.escalation_gate import EscalationGateExecutor
from limen.agents.executors.fire_check import FireCheckExecutor
from limen.agents.executors.meteo_fetch import MeteoFetchExecutor
from limen.agents.executors.persist_result import PersistResultExecutor
from limen.agents.executors.risk_scoring import RiskScoringExecutor
from limen.agents.executors.seismic_check import SeismicCheckExecutor
from limen.agents.executors.sensor_fetch import SensorFetchExecutor
from limen.agents.executors.static_factors import StaticFactorsExecutor

__all__ = [
    "AlertDispatchExecutor",
    "AreaResolverExecutor",
    "EscalationGateExecutor",
    "FireCheckExecutor",
    "MeteoFetchExecutor",
    "PersistResultExecutor",
    "RiskScoringExecutor",
    "SeismicCheckExecutor",
    "SensorFetchExecutor",
    "StaticFactorsExecutor",
]
