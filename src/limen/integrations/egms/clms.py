"""L'archivio EGMS con la chiave di servizio del Copernicus Land Monitoring Service.

Login, ricerche, download a blocchi, ritentativi e cache su disco vengono dal
pacchetto ``egms-client`` (estratto da Limen, Apache-2.0). Qui resta solo
come Limen trova la chiave (``EGMS__SERVICE_KEY`` o ``EGMS__SERVICE_KEY_FILE``)
e quale client HTTP usa: quello condiviso di tutte le integrazioni.
"""

from __future__ import annotations

from pathlib import Path

from egms_client import EgmsArchive, ServiceKey

from limen.config.settings import EgmsSettings
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient

log = get_logger(__name__)


def leggi_chiave(testo: str) -> ServiceKey | None:
    """La chiave di servizio dal JSON, ``None`` se vuota o incompleta."""
    if not testo.strip():
        return None
    try:
        return ServiceKey.from_json(testo)
    except ValueError as exc:
        # Impostata ma illeggibile (PEM troncato, virgolette perse nel .env):
        # senza questo log il sync direbbe solo «nessuna chiave».
        log.warning("egms.chiave_non_valida", error=str(exc)[:200])
        return None


def chiave(s: EgmsSettings) -> ServiceKey | None:
    """La chiave dalla variabile o dal file; ``None`` se nessuno dei due la dà."""
    if s.service_key is not None and s.service_key.get_secret_value().strip():
        return leggi_chiave(s.service_key.get_secret_value())
    if s.service_key_file and s.service_key_file.strip():
        try:
            return leggi_chiave(Path(s.service_key_file).expanduser().read_text())
        except OSError as exc:
            log.warning("egms.file_chiave_illeggibile", path=s.service_key_file, error=str(exc))
    return None


async def archivio(s: EgmsSettings) -> EgmsArchive | None:
    """L'archivio sul client HTTP condiviso, o ``None`` senza chiave."""
    trovata = chiave(s)
    if trovata is None:
        return None
    return EgmsArchive(await SharedHttpClient.get(), trovata, archive_url=s.archive_url)


def perche_no(s: EgmsSettings) -> str:
    """Il motivo, per il log, per cui non c'è un archivio."""
    if s.token is not None and s.token.get_secret_value().strip():
        return "EGMS__TOKEN non è più supportato (scadeva): serve EGMS__SERVICE_KEY"
    if s.attivo:
        return "chiave EGMS impostata ma illeggibile"
    return "né EGMS__SERVICE_KEY né EGMS__SERVICE_KEY_FILE"


__all__ = ["archivio", "chiave", "leggi_chiave", "perche_no"]
