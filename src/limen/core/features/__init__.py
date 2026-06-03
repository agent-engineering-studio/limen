"""Feature-assembly layer.

Turns the workflow's :class:`MonitoringContext` (plus per-cell static
factors loaded by the ``StaticFactors`` executor) into one
:class:`CellFeatureBundle` per cell, ready for the deterministic
:class:`MultiFactorScoringEngine`.

This is the *single* assembly path. When the V2 ML engine lands it
will consume the same bundles built here, giving us train/serve
parity for free.
"""

from limen.core.features.assembler import assemble_bundles

__all__ = ["assemble_bundles"]
