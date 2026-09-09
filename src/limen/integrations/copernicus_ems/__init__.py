"""Copernicus EMS Rapid Mapping — attivazioni, perimetri allagati, maschere."""

from limen.integrations.copernicus_ems.client import (
    Activation,
    ObservationMask,
    ObservedFlood,
    fetch_activations,
    fetch_observation_masks,
    fetch_observed_floods,
)

__all__ = [
    "Activation",
    "ObservationMask",
    "ObservedFlood",
    "fetch_activations",
    "fetch_observation_masks",
    "fetch_observed_floods",
]
