"""Copernicus EMS Rapid Mapping — attivazioni, perimetri allagati, maschere."""

from limen.integrations.copernicus_ems.client import (
    Activation,
    ActivationTruth,
    ObservationMask,
    ObservedFlood,
    fetch_activation_truth,
    fetch_activations,
)

__all__ = [
    "Activation",
    "ActivationTruth",
    "ObservationMask",
    "ObservedFlood",
    "fetch_activation_truth",
    "fetch_activations",
]
