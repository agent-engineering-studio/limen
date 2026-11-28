"""Spostato in limen-core: `limen_core.scoring.wildfire.confronto`.

Questo nome resta per il codice che lo importa. È lo stesso modulo, non una
copia: chi lo sostituisce nei test sostituisce quello vero.
"""

import sys

from limen_core.scoring.wildfire import confronto as _spostato
from limen_core.scoring.wildfire.confronto import *  # noqa: F403

sys.modules[__name__] = _spostato
