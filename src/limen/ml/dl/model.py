"""1D-CNN over a 168-hour rainfall window (ITALICA-informed, V2.2).

The architecture is intentionally small — a handful of conv layers
followed by a sigmoid head — so the model fits in tens of KB once
exported to ONNX and runs at single-digit ms per cell on CPU. PyTorch
is imported lazily so the package can be inspected without `dl`
installed.
"""

from __future__ import annotations

from typing import Any

SEQUENCE_LENGTH_HOURS = 168
"""One full week of hourly rainfall — long enough to capture the rolling
antecedent that triggers most Italian flow-type landslides."""


def build_rainfall_cnn() -> Any:
    """Return a fresh untrained 1D-CNN. Caller installs the optimiser."""
    import torch
    import torch.nn as nn

    class RainfallCNN(nn.Module):  # type: ignore[misc, unused-ignore]
        def __init__(self) -> None:
            super().__init__()
            self.net = nn.Sequential(
                nn.Conv1d(in_channels=1, out_channels=16, kernel_size=5, padding=2),
                nn.ReLU(),
                nn.MaxPool1d(2),
                nn.Conv1d(16, 32, kernel_size=5, padding=2),
                nn.ReLU(),
                nn.MaxPool1d(2),
                nn.Conv1d(32, 64, kernel_size=5, padding=2),
                nn.ReLU(),
                nn.AdaptiveAvgPool1d(1),
                nn.Flatten(),
                nn.Linear(64, 32),
                nn.ReLU(),
                nn.Linear(32, 1),
            )

        def forward(self, x: Any) -> Any:
            logit = self.net(x)
            return torch.sigmoid(logit).squeeze(-1)

    return RainfallCNN()


__all__ = ["SEQUENCE_LENGTH_HOURS", "build_rainfall_cnn"]
