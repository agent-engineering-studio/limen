"""ONNX-runtime wrapper used by the V2 ML engine for the M component.

`onnxruntime` is in the `ml` optional group; without it the class
falls back to a deterministic neutral probability so the workflow
never crashes. The engine handles missing rainfall by passing a
zero-padded window of :data:`SEQUENCE_LENGTH_HOURS`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from limen.core.logging import get_logger
from limen.ml.dl.model import SEQUENCE_LENGTH_HOURS

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


class DLMeteoProbability:
    """Load an ONNX rainfall model + ``predict(window) → probability``.

    A *neutral* probability of 0.5 is returned when the ONNX session
    can't be initialised — the rest of the engine treats this as "no
    signal", which is the desired conservative degradation.
    """

    def __init__(self, model_path: Path) -> None:
        self._model_path = model_path
        self._session: Any = None
        self._input_name: str = "rainfall_window"

    @property
    def sequence_length(self) -> int:
        return SEQUENCE_LENGTH_HOURS

    @property
    def model_path(self) -> Path:
        return self._model_path

    def _ensure_session(self) -> None:
        if self._session is not None:
            return
        try:
            import onnxruntime as ort
        except ImportError as exc:
            _log.warning(
                "dl.serve.skip",
                error=str(exc),
                hint="install the `ml` dependency group",
            )
            return
        if not self._model_path.exists():
            _log.warning("dl.serve.missing_model", path=str(self._model_path))
            return
        try:
            self._session = ort.InferenceSession(
                str(self._model_path), providers=["CPUExecutionProvider"]
            )
            self._input_name = self._session.get_inputs()[0].name
        except Exception as exc:
            _log.warning("dl.serve.load_failed", error=str(exc), path=str(self._model_path))

    def predict(self, window: list[float]) -> float:
        """Return P(landslide | window). Neutral 0.5 on any failure."""
        self._ensure_session()
        if self._session is None:
            return 0.5
        try:
            import numpy as np
        except ImportError:  # pragma: no cover
            return 0.5
        padded = _pad_or_trim(window, length=self.sequence_length)
        arr = np.asarray(padded, dtype=np.float32).reshape(1, 1, self.sequence_length)
        try:
            outputs = self._session.run(None, {self._input_name: arr})
        except Exception as exc:
            _log.warning("dl.serve.predict_failed", error=str(exc))
            return 0.5
        return float(np.asarray(outputs[0]).flatten()[0])


def _pad_or_trim(values: list[float], *, length: int) -> list[float]:
    if len(values) >= length:
        return [float(v) for v in values[-length:]]
    return [0.0] * (length - len(values)) + [float(v) for v in values]


__all__ = ["DLMeteoProbability"]
