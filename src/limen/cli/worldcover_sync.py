"""`limen worldcover-sync` — ESA WorldCover sull'Italia, per ``firms_client.trust`` (#714).

Scarica le tile intere che coprono ``FIRMS__BBOX`` (~1,3 GB la prima volta) in
``$DATA_ROOT/firms-client/worldcover``; un giro ripetuto non riscarica
niente (chiede solo le tile di mare, che rispondono 404).
Esce con 1 se una tile non è arrivata: le altre restano, il prossimo giro
riprova solo quelle.
"""

from __future__ import annotations

from limen.core.logging import get_logger
from limen.integrations.firms.worldcover import cartella_worldcover, scarica_worldcover

log = get_logger(__name__)


async def run() -> int:
    esito = await scarica_worldcover()
    log.info(
        "worldcover.sync",
        cartella=str(cartella_worldcover()),
        scaricate=len(esito.scaricate),
        presenti=len(esito.presenti),
        assenti=len(esito.assenti),
        fallite=esito.fallite,
    )
    return 1 if esito.fallite else 0
