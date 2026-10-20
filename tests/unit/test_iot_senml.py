"""Protocollo v2 dei sensori (#252): parser SenML, limite di frequenza, topic."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import cbor2
import pytest

from limen.integrations.iot.ingestore_v2 import Esito, LimiteFrequenza, _topic
from limen.integrations.iot.schemas import ObservedProperty
from limen.integrations.iot.senml import SenmlError, analizza, cbor_a_json

ID = "pluvio-matera-01"
ADESSO = datetime(2026, 10, 16, 10, 0, tzinfo=UTC)
BT = int(ADESSO.timestamp())


def _payload(*records: dict[str, Any]) -> bytes:
    return json.dumps(list(records)).encode()


def test_messaggio_del_protocollo() -> None:
    msg = analizza(
        _payload(
            {"bn": f"{ID}/", "bt": BT, "n": "rainfall", "u": "mm", "v": 0.4},
            {"n": "soil_moisture", "u": "m3/m3", "v": 0.31, "t": -60},
            {"n": "seq", "v": 18342},
        ),
        device_id=ID,
        ricevuto=ADESSO,
    )
    assert msg.sequenza == 18342
    assert [(m.grandezza, m.valore) for m in msg.misure] == [
        (ObservedProperty.RAINFALL, 0.4),
        (ObservedProperty.SOIL_MOISTURE, 0.31),
    ]
    assert msg.misure[0].istante == ADESSO
    assert msg.misure[1].istante == ADESSO - timedelta(minutes=1)


def test_nome_completo_senza_bn_e_unita_di_base() -> None:
    msg = analizza(
        _payload(
            {"bu": "mm", "n": f"{ID}/rainfall", "v": 1.2, "t": BT},
            {"n": f"{ID}/seq", "v": 1},
        ),
        device_id=ID,
        ricevuto=ADESSO,
    )
    assert msg.misure[0].unita == "mm"
    assert msg.misure[0].istante == ADESSO


def test_tempo_relativo_all_arrivo() -> None:
    """RFC 8428: sotto 2**28 il tempo è relativo all'istante di arrivo."""
    msg = analizza(
        _payload(
            {"bn": f"{ID}/", "n": "rainfall", "u": "mm", "v": 0.2, "t": -300}, {"n": "seq", "v": 2}
        ),
        device_id=ID,
        ricevuto=ADESSO,
    )
    assert msg.misure[0].istante == ADESSO - timedelta(minutes=5)


def test_grandezza_sconosciuta_ignorata_non_rifiutata() -> None:
    msg = analizza(
        _payload(
            {"bn": f"{ID}/", "bt": BT, "n": "snow_depth", "u": "cm", "v": 1.0},
            {"n": "rainfall", "u": "mm", "v": 0.0},
            {"n": "seq", "v": 3},
        ),
        device_id=ID,
        ricevuto=ADESSO,
    )
    assert msg.ignorate == ("snow_depth",)
    assert len(msg.misure) == 1


def test_grandezze_per_alluvione_e_incendio() -> None:
    """#254: idrometro e stazione meteo passano con le unità del protocollo."""
    msg = analizza(
        _payload(
            {"bn": f"{ID}/", "bt": BT, "n": "water_level", "u": "m", "v": 1.85},
            {"n": "air_temperature", "u": "Cel", "v": 33.2},
            {"n": "relative_humidity", "u": "%", "v": 21.0},
            {"n": "wind_speed", "u": "km/h", "v": 27.5},
            {"n": "seq", "v": 4},
        ),
        device_id=ID,
        ricevuto=ADESSO,
    )
    assert msg.ignorate == ()
    assert [m.grandezza for m in msg.misure] == [
        ObservedProperty.WATER_LEVEL,
        ObservedProperty.AIR_TEMPERATURE,
        ObservedProperty.RELATIVE_HUMIDITY,
        ObservedProperty.WIND_SPEED,
    ]


def test_temperatura_in_gradi_con_simbolo_si_scarta() -> None:
    with pytest.raises(SenmlError, match="Cel"):
        analizza(
            _payload(
                {"bn": f"{ID}/", "bt": BT, "n": "air_temperature", "u": "°C", "v": 20.0},
                {"n": "seq", "v": 5},
            ),
            device_id=ID,
            ricevuto=ADESSO,
        )


@pytest.mark.parametrize(
    ("records", "motivo"),
    [
        (
            [
                {"bn": "altro-dispositivo/", "bt": BT, "n": "rainfall", "u": "mm", "v": 1},
                {"n": "seq", "v": 1},
            ],
            "dispositivo",
        ),
        (
            [{"bn": f"{ID}/", "bt": BT, "n": "rainfall", "u": "in", "v": 1}, {"n": "seq", "v": 1}],
            "unità",
        ),
        ([{"bn": f"{ID}/", "bt": BT, "n": "rainfall", "v": 1}, {"n": "seq", "v": 1}], "unità"),
        ([{"bn": f"{ID}/", "bt": BT, "n": "rainfall", "u": "mm", "v": 1}], "seq"),
        ([{"bn": f"{ID}/", "n": "seq", "v": 1}, {"n": "seq", "v": 2}], "seq"),
        ([{"bn": f"{ID}/", "n": "seq", "v": -1}], "seq"),
        ([{"bn": f"{ID}/", "n": "seq", "v": 1.5}], "seq"),
        (
            [
                {"bn": f"{ID}/", "bt": BT, "n": "rainfall", "u": "mm", "v": True},
                {"n": "seq", "v": 1},
            ],
            "numerico",
        ),
        (
            [
                {"bn": f"{ID}/", "bt": BT, "n": "rainfall", "u": "mm", "vs": "1"},
                {"n": "seq", "v": 1},
            ],
            "valore",
        ),
        (
            [
                {"bn": f"{ID}/", "bt": BT, "n": "rainfall", "u": "mm", "v": 1, "bver_": 10},
                {"n": "seq", "v": 1},
            ],
            "capire",
        ),
        (
            [
                {"bn": f"{ID}/", "bt": 1e300, "n": "rainfall", "u": "mm", "v": 1},
                {"n": "seq", "v": 1},
            ],
            "tempo",
        ),
        ([], "array"),
        (["rainfall"], "oggetto"),
    ],
)
def test_messaggi_da_scartare(records: list[Any], motivo: str) -> None:
    with pytest.raises(SenmlError, match=motivo):
        analizza(json.dumps(records).encode(), device_id=ID, ricevuto=ADESSO)


@pytest.mark.parametrize("payload", [b"{not json", b"\xff\xfe", b'{"n": "seq", "v": 1}', b"[NaN]"])
def test_payload_non_senml(payload: bytes) -> None:
    with pytest.raises(SenmlError):
        analizza(payload, device_id=ID, ricevuto=ADESSO)


def test_valore_non_finito() -> None:
    with pytest.raises(SenmlError, match="finito"):
        analizza(
            b'[{"bn": "pluvio-matera-01/", "n": "rainfall", "u": "mm", "v": Infinity},'
            b' {"n": "seq", "v": 1}]',
            device_id=ID,
            ricevuto=ADESSO,
        )


@pytest.mark.parametrize(
    "payload",
    [
        b"[" * 3000 + b"]" * 3000,
        b'[{"bn": "pluvio-matera-01/", "n": "rainfall", "u": "mm", "v": 1'
        + b"0" * 400
        + b'}, {"n": "seq", "v": 1}]',
        b'[{"bn": "pluvio-matera-01/", "n": "seq", "v": 9223372036854775808}]',
    ],
    ids=["annidamento", "intero-enorme", "seq-oltre-bigint"],
)
def test_payload_ostili_sono_malformati(payload: bytes) -> None:
    """Payload che un terzo può costruire in 2 KB: devono essere scarti, non
    errori del worker."""
    with pytest.raises(SenmlError):
        analizza(payload, device_id=ID, ricevuto=ADESSO)


def test_limite_di_frequenza_e_quarantena() -> None:
    limite = LimiteFrequenza(al_minuto=3, scarti_per_quarantena=4)
    t = ADESSO
    assert [limite.valuta(ID, t + timedelta(seconds=i)) for i in range(3)] == [None] * 3
    # Oltre il limite si scarta; gli scarti ripetuti portano alla quarantena.
    esiti = [limite.valuta(ID, t + timedelta(seconds=10 + i)) for i in range(4)]
    assert esiti == [Esito.FREQUENZA] * 3 + [Esito.QUARANTENA]
    # Un altro dispositivo non ne risente.
    assert limite.valuta("altro-dispositivo", t + timedelta(seconds=20)) is None
    # Passato il minuto la finestra si libera.
    assert limite.valuta(ID, t + timedelta(minutes=1, seconds=15)) is None


@pytest.mark.parametrize(
    ("topic", "atteso"),
    [
        ("limen/v2/pluvio-matera-01/obs", ("pluvio-matera-01", "obs")),
        ("limen/v2/pluvio-matera-01/status", ("pluvio-matera-01", "status")),
        ("limen/v1/puglia/bari/thing/rainfall/obs", None),
        ("limen/v2/pluvio-matera-01/obs/extra", None),
        ("limen/v2/Pluvio/obs", None),
        ("limen/v2/pluvio-matera-01/cmd", None),
    ],
)
def test_topic(topic: str, atteso: tuple[str, str] | None) -> None:
    assert _topic(topic) == atteso


def test_cbor_come_json() -> None:
    """RFC 8428 §6: le etichette intere diventano i nomi JSON (#266)."""
    cbor = cbor2.dumps(
        [{-2: f"{ID}/", -3: 1792065600, 0: "rainfall", 1: "mm", 2: 0.4}, {0: "seq", 2: 7}]
    )
    assert json.loads(cbor_a_json(cbor)) == [
        {"bn": f"{ID}/", "bt": 1792065600, "n": "rainfall", "u": "mm", "v": 0.4},
        {"n": "seq", "v": 7},
    ]
    messaggio = analizza(cbor_a_json(cbor), device_id=ID, ricevuto=ADESSO)
    assert messaggio.sequenza == 7
    assert [(m.grandezza, m.valore) for m in messaggio.misure] == [(ObservedProperty.RAINFALL, 0.4)]


def test_cbor_campi_testuali_e_obbligatori() -> None:
    """Un campo con nome testuale segue le regole JSON: «_» finale scarta tutto."""
    ignoto = cbor2.dumps([{-2: f"{ID}/", 0: "seq", 2: 1, "nota": "x"}])
    assert json.loads(cbor_a_json(ignoto))[0]["nota"] == "x"
    obbligatorio = cbor_a_json(cbor2.dumps([{-2: f"{ID}/", 0: "seq", 2: 1, "rif_": 1}]))
    with pytest.raises(SenmlError):
        analizza(obbligatorio, device_id=ID, ricevuto=ADESSO)


@pytest.mark.parametrize(
    "valore",
    [
        {"a": 1},
        [[1]],
        [{-2: f"{ID}/", 0: "seq", 2: 1, 42: 1}],
        [{-2: f"{ID}/", 0: "seq", 2: 1, 1.5: 1}],
        [{-2: f"{ID}/", 0: "seq", 8: b"\x00"}],
        [{-2: f"{ID}/", 0: "seq", 2: float("nan")}],
        [{-2: f"{ID}/", 0: "seq", 2: cbor2.CBORTag(1234, 1)}],
        # Tag che cbor2 decodifica da sé: regex, bigfloat, decimale, MIME, UUID.
        [{-2: f"{ID}/", 0: "seq", 2: cbor2.CBORTag(35, "(")}],
        [{-2: f"{ID}/", 0: "seq", 2: cbor2.CBORTag(5, [10**9, 1])}],
        [{-2: f"{ID}/", 0: "seq", 2: cbor2.CBORTag(4, [10**9, 1])}],
        [{-2: f"{ID}/", 0: "seq", 2: cbor2.CBORTag(36, "x")}],
        [{-2: f"{ID}/", 0: "seq", 2: cbor2.CBORTag(37, b"x")}],
    ],
    ids=[
        "mappa",
        "non_mappa",
        "etichetta_ignota",
        "etichetta_float",
        "byte",
        "nan",
        "tag",
        "regex",
        "bigfloat",
        "decimale",
        "mime",
        "uuid",
    ],
)
def test_cbor_rifiutato(valore: Any) -> None:
    with pytest.raises(SenmlError):
        cbor_a_json(cbor2.dumps(valore))


@pytest.mark.parametrize("grezzo", [b"", b"\xff", b"\x9b\xff\xff\xff\xff\xff\xff\xff\xff"])
def test_cbor_illeggibile(grezzo: bytes) -> None:
    with pytest.raises(SenmlError):
        cbor_a_json(grezzo)
