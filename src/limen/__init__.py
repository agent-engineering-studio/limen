"""Limen — AI multi-factor landslide-risk monitoring."""

from importlib import metadata
from pathlib import Path

from limen_core import calibration

# I motori di punteggio stanno in limen-core e non portano tarature: le soglie
# e i pesi restano qui, in `limen.config`. Va detto prima di ogni altro import.
calibration.use(Path(__file__).parent / "config")

try:
    __version__: str = metadata.version("limen")
except metadata.PackageNotFoundError:  # pragma: no cover - source checkout
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
