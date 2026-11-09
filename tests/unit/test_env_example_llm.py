"""Document every LLM setting, including per-role model overrides."""

import json
import re
from io import StringIO
from pathlib import Path

import pytest
from dotenv import dotenv_values
from pydantic import TypeAdapter
from pydantic_settings import BaseSettings

from limen.config.settings import LLMSettings

EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def _assignments() -> dict[str, str]:
    return dict(
        re.findall(
            r"^\s*#?\s*([A-Z][A-Z0-9_]+)=(.*)$",
            EXAMPLE.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )


def _setting_names(model: type[BaseSettings], prefix: str) -> set[str]:
    names = set()
    for name, field in model.model_fields.items():
        key = f"{prefix}__{name.upper()}"
        if isinstance(field.annotation, type) and issubclass(field.annotation, BaseSettings):
            names.update(_setting_names(field.annotation, key))
        else:
            names.add(key)
    return names


def test_env_example_documents_every_llm_setting() -> None:
    expected = _setting_names(LLMSettings, "LLM")
    assert not (missing := expected - _assignments().keys()), sorted(missing)


@pytest.mark.parametrize(
    "name",
    [
        "briefing_min_level",
        "briefing_min_hours",
        "ollama_timeout_seconds",
        "anthropic_prezzi_usd_mtok",
        "anthropic_sconto_batch",
        "eventi_titoli_massimi",
        "eventi_attesa_massima_minuti",
    ],
)
def test_llm_examples_use_valid_current_defaults(name: str) -> None:
    key = f"LLM__{name.upper()}"
    literal = _assignments()[key]
    raw = dotenv_values(stream=StringIO(f"{key}={literal}"))[key]
    assert raw is not None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    field = LLMSettings.model_fields[name]
    assert TypeAdapter(field.annotation).validate_python(value) == field.get_default(
        call_default_factory=True
    )
