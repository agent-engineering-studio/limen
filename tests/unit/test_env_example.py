"""The scheduler example stays complete as settings evolve."""

import json
import re
from io import StringIO
from pathlib import Path

import pytest
from dotenv import dotenv_values
from pydantic import TypeAdapter

from limen.config.settings import SchedulerSettings

EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def _assignments() -> dict[str, str]:
    return dict(
        re.findall(
            r"^\s*#?\s*([A-Z][A-Z0-9_]+)=(.*)$",
            EXAMPLE.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )


def test_env_example_documents_every_scheduler_setting() -> None:
    expected = {f"SCHEDULER__{name.upper()}" for name in SchedulerSettings.model_fields}
    assert not (missing := expected - _assignments().keys()), sorted(missing)


@pytest.mark.parametrize(
    "name",
    [
        "enable_hourly_monitoring",
        "hourly_monitoring_minutes",
        "job_runs_retention_days",
        "enable_dpc_bollettini",
        "dpc_bollettini_minutes",
        "ingv_sync_minutes",
        "ingv_sync_ritardo_massimo_minuti",
        "ingv_bbox",
        "glofas_chiamate_per_notte",
        "forecast_cells_hours_utc",
        "forecast_cells_minute",
    ],
)
def test_scheduler_examples_use_valid_current_defaults(name: str) -> None:
    key = f"SCHEDULER__{name.upper()}"
    literal = _assignments()[key]
    raw = dotenv_values(stream=StringIO(f"{key}={literal}"))[key]
    assert raw is not None
    value = json.loads(raw)
    field = SchedulerSettings.model_fields[name]
    assert TypeAdapter(field.annotation).validate_python(value) == field.get_default(
        call_default_factory=True
    )
