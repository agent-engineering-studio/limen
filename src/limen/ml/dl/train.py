"""Offline DL training + ONNX export (V2.2).

Inputs: per-event rainfall windows (length :data:`SEQUENCE_LENGTH_HOURS`,
ending at the event time) labelled 1/0. Walk the IFFI inventory + a
balanced background sample exactly like :mod:`limen.ml.feature_store`,
but pull the *time series* rather than the static features.

Output: ``rainfall_cnn.onnx`` written to disk (configurable path) +
logged as an MLflow artefact when MLflow is available.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from limen.core.logging import get_logger
from limen.ml.dl.model import SEQUENCE_LENGTH_HOURS, build_rainfall_cnn

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DLTrainResult:
    onnx_path: Path | None
    epochs: int
    final_loss: float


def train_rainfall_cnn(
    *,
    sequences: Any,
    labels: Any,
    epochs: int = 12,
    batch_size: int = 64,
    learning_rate: float = 1e-3,
    onnx_path: Path | None = None,
) -> DLTrainResult:
    """Train the small 1D-CNN and (optionally) export to ONNX.

    Accepts numpy arrays (``sequences`` shape ``[N, T]``, ``labels``
    shape ``[N]``) so callers don't need to materialise torch tensors
    themselves.
    """
    try:
        import numpy as np
        import torch
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as exc:
        _log.warning("dl.train.skip", error=str(exc), hint="install the `dl` group")
        return DLTrainResult(onnx_path=None, epochs=0, final_loss=0.0)

    if len(sequences) == 0 or sequences.shape[1] != SEQUENCE_LENGTH_HOURS:
        _log.warning(
            "dl.train.bad_input",
            n=len(sequences),
            expected_length=SEQUENCE_LENGTH_HOURS,
        )
        return DLTrainResult(onnx_path=None, epochs=0, final_loss=0.0)

    x = torch.tensor(np.asarray(sequences, dtype=float), dtype=torch.float32).unsqueeze(1)
    y = torch.tensor(np.asarray(labels, dtype=float), dtype=torch.float32)
    loader = DataLoader(TensorDataset(x, y), batch_size=batch_size, shuffle=True)

    model = build_rainfall_cnn()
    optimiser = torch.optim.Adam(model.parameters(), lr=learning_rate)
    loss_fn = torch.nn.BCELoss()
    final_loss = 0.0
    for epoch in range(epochs):
        running = 0.0
        for batch_x, batch_y in loader:
            optimiser.zero_grad()
            preds = model(batch_x)
            loss = loss_fn(preds, batch_y)
            loss.backward()
            optimiser.step()
            running += float(loss.item())
        final_loss = running / max(len(loader), 1)
        _log.info("dl.train.epoch", epoch=epoch, loss=final_loss)

    saved: Path | None = None
    if onnx_path is not None:
        saved = _export_onnx(model, onnx_path)
    return DLTrainResult(onnx_path=saved, epochs=epochs, final_loss=final_loss)


def _export_onnx(model: Any, dest: Path) -> Path | None:
    try:
        import torch
    except ImportError:  # pragma: no cover
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros((1, 1, SEQUENCE_LENGTH_HOURS), dtype=torch.float32)
    try:
        torch.onnx.export(
            model,
            dummy,
            str(dest),
            input_names=["rainfall_window"],
            output_names=["probability"],
            dynamic_axes={"rainfall_window": {0: "batch"}, "probability": {0: "batch"}},
            opset_version=17,
        )
    except Exception as exc:  # pragma: no cover
        _log.warning("dl.export.failed", error=str(exc), path=str(dest))
        return None
    _log.info("dl.export.done", path=str(dest))
    return dest


__all__ = ["DLTrainResult", "train_rainfall_cnn"]
