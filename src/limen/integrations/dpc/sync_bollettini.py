"""Sincronizzazione del bollettino DPC: idempotente sul nome del file.

Lo stesso bollettino letto due volte non riscrive niente
(`dataset_versions`); un «Aggiornamento» dello stesso giorno ha un nome
nuovo e sostituisce le righe del suo giorno.
"""

from __future__ import annotations

from typing import Any

from limen.core.logging import get_logger
from limen.data.repos import dataset_versions_repo, dpc_allerte_repo
from limen.integrations.dpc.bollettini import scarica, ultimo_nome

log = get_logger(__name__)

SOURCE = "dpc"
DATASET = "bollettino-criticita"


async def run_sync_bollettini() -> dict[str, Any]:
    nome = await ultimo_nome()
    if nome is None:
        return {"skipped": True, "reason": "non raggiungibile"}
    if await dataset_versions_repo.find(SOURCE, DATASET, nome) is not None:
        return {"skipped": True, "reason": "già importato", "bollettino": nome}
    bollettino = await scarica(nome)
    if bollettino is None or not bollettino.zones:
        return {"skipped": True, "reason": "vuoto o illeggibile", "bollettino": nome}
    zone = await dpc_allerte_repo.scrivi(bollettino)
    await dataset_versions_repo.record(
        source=SOURCE,
        dataset=DATASET,
        version=nome,
        valid_from=bollettino.issued,
        metadata={"zone": zone, "allerte": sum(z.level > 0 for z in bollettino.zones)},
    )
    log.info(
        "dpc.bollettino.imported",
        bollettino=bollettino.name,
        zone=zone,
        allerte=sum(z.level > 0 for z in bollettino.zones),
    )
    return {"skipped": False, "bollettino": bollettino.name, "zone": zone}
