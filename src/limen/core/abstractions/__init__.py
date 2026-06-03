"""Protocol definitions for external sources.

Each external integration implements one of these Protocols. Application
code depends on the Protocol, never on the concrete implementation, so
the integrations can be swapped (or mocked in tests) without touching
callers.
"""

from limen.core.abstractions.external import (
    EffisClient,
    IdroGeoClient,
    IngvClient,
    OpenMeteoClient,
)

__all__ = [
    "EffisClient",
    "IdroGeoClient",
    "IngvClient",
    "OpenMeteoClient",
]
