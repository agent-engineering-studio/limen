"""L'ingestore v2 tiene una sessione MQTT persistente (#273).

Con una sessione pulita il broker conferma ai dispositivi i messaggi che
arrivano mentre il worker è giù e poi li butta: il firmware, ricevuta la
conferma, non li rimanda, e le misure di ogni deploy spariscono senza traccia.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from limen.config.settings import IotCittadiniSettings, IotSettings
from limen.integrations.iot import ingestore_v2


async def test_sessione_persistente_e_conferma_dopo_il_salvataggio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visti: dict[str, Any] = {}

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            visti.update(kwargs)
            self._client = SimpleNamespace(manual_ack_set=lambda on: visti.update(manual_ack=on))

        async def __aenter__(self) -> _Client:
            raise asyncio.CancelledError

        async def __aexit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(ingestore_v2.aiomqtt, "Client", _Client)
    ingestore = ingestore_v2.IngestoreV2(IotSettings(cittadini=IotCittadiniSettings(enabled=True)))

    with pytest.raises(asyncio.CancelledError):
        await ingestore._run()

    assert visti["clean_session"] is False
    assert visti["identifier"] == "limen-ingestore-v2"
    # Confermare prima di salvare perderebbe il messaggio a uno stop.
    assert visti["manual_ack"] is True
