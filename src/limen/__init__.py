"""Limen — AI multi-factor landslide-risk monitoring."""

from importlib import metadata

try:
    __version__: str = metadata.version("limen")
except metadata.PackageNotFoundError:  # pragma: no cover - source checkout
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
