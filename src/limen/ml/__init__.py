"""V2 — ML engine + feature store + training pipeline.

Public surface assembled here for convenience. The heavy ML deps
(``lightgbm``, ``mlflow``, ``optuna``, ``shap``, ``onnxruntime``) are
imported lazily from each submodule — installing the optional ``ml``
group is only required to run :mod:`limen.ml.train`.
"""

from limen.ml.feature_store import (
    SpatialBlockGrid,
    extract_training_samples,
)

__all__ = [
    "SpatialBlockGrid",
    "extract_training_samples",
]
