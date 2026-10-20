"""La firma dei messaggi che i sensori consegnano via HTTP (#265).

Il dispositivo firma, con la chiave della sua CSR, i byte

    limen-v2\\n{id}\\n{tempo}\\n{corpo}

dove ``tempo`` sono i secondi Unix dell'invio, scritti in decimale, e
``corpo`` è il SenML così come viaggia. L'id e il tempo stanno dentro la
firma perché la stessa misura firmata per un dispositivo non deve valere per
un altro, e una firma vecchia non deve poter essere rimandata dopo la finestra.

Due tipi di chiave, quelli che la registrazione accetta:

* **P-256** (ECDSA su SHA-256): la chiave del secure element ATECC608, lo
  stesso dispositivo che parla MQTT. La firma arriva DER, oppure grezza come la
  restituisce il secure element: 64 byte, ``r || s``.
* **Ed25519**: 64 byte, per i dispositivi che parlano solo HTTP.
"""

from __future__ import annotations

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.serialization import load_der_public_key

_PREFISSO = b"limen-v2\n"


def messaggio_firmato(device_id: str, tempo: int, corpo: bytes) -> bytes:
    return b"%s%s\n%d\n%s" % (_PREFISSO, device_id.encode(), tempo, corpo)


def verifica(chiave_der: bytes, firma: bytes, messaggio: bytes) -> bool:
    """Vero solo per una firma valida di una chiave P-256 o Ed25519."""
    try:
        chiave = load_der_public_key(chiave_der)
    except (ValueError, UnsupportedAlgorithm):
        return False
    try:
        if isinstance(chiave, ed25519.Ed25519PublicKey):
            chiave.verify(firma, messaggio)
            return True
        if isinstance(chiave, ec.EllipticCurvePublicKey) and chiave.curve.name == "secp256r1":
            if len(firma) == 64:
                firma = encode_dss_signature(
                    int.from_bytes(firma[:32], "big"), int.from_bytes(firma[32:], "big")
                )
            chiave.verify(firma, messaggio, ec.ECDSA(hashes.SHA256()))
            return True
    except (InvalidSignature, ValueError):
        return False
    return False


__all__ = ["messaggio_firmato", "verifica"]
