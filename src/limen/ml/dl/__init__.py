"""DL sub-model for rainfall sequences (V2.2).

ITALICA-informed 1D-CNN trained offline (PyTorch), exported to ONNX,
served via :mod:`onnxruntime` inside :class:`DLMeteoProbability`. Feeds
the M component of the V2 ML engine.
"""

from limen.ml.dl.serve import DLMeteoProbability

__all__ = ["DLMeteoProbability"]
