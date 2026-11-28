"""Spostato in limen-core: `limen_core.models.hazard`.

Questo nome resta per il codice che lo importa. È lo stesso modulo, non una
copia: chi lo sostituisce nei test sostituisce quello vero.
"""

import sys

from limen_core.models import hazard as _spostato
from limen_core.models.hazard import *  # noqa: F403

sys.modules[__name__] = _spostato
