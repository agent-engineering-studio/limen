"""Spostato in limen-core: `limen_core.scoring.flood.climatologia`.

Questo nome resta per il codice che lo importa. È lo stesso modulo, non una
copia: chi lo sostituisce nei test sostituisce quello vero.
"""

import sys

from limen_core.scoring.flood import climatologia as _spostato
from limen_core.scoring.flood.climatologia import *  # noqa: F403

sys.modules[__name__] = _spostato
