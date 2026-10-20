"""Firma dell'ingresso HTTP dei sensori (#265): P-256 ed Ed25519."""

from __future__ import annotations

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from limen.integrations.iot.firma_http import messaggio_firmato, verifica

CORPO = b'[{"bn":"pluvio-matera-01/","n":"rainfall","u":"mm","v":0.4},{"n":"seq","v":1}]'
MSG = messaggio_firmato("pluvio-matera-01", 1780313400, CORPO)


def _der(
    chiave: ed25519.Ed25519PrivateKey | ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey,
) -> bytes:
    return chiave.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def test_messaggio_firmato_contiene_id_tempo_e_corpo() -> None:
    assert MSG == b"limen-v2\npluvio-matera-01\n1780313400\n" + CORPO


def test_ed25519() -> None:
    chiave = ed25519.Ed25519PrivateKey.generate()
    assert verifica(_der(chiave), chiave.sign(MSG), MSG)


def test_p256_der_e_grezza() -> None:
    """Il secure element restituisce r||s su 64 byte, una libreria il DER."""
    chiave = ec.generate_private_key(ec.SECP256R1())
    der = chiave.sign(MSG, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    grezza = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    assert verifica(_der(chiave), der, MSG)
    assert verifica(_der(chiave), grezza, MSG)


def test_firma_di_un_altro_messaggio_o_di_un_altra_chiave() -> None:
    chiave = ed25519.Ed25519PrivateKey.generate()
    altra = ed25519.Ed25519PrivateKey.generate()
    firma = chiave.sign(MSG)
    assert not verifica(
        _der(chiave), firma, messaggio_firmato("pluvio-matera-02", 1780313400, CORPO)
    )
    assert not verifica(
        _der(chiave), firma, messaggio_firmato("pluvio-matera-01", 1780313401, CORPO)
    )
    assert not verifica(_der(altra), firma, MSG)


def test_chiavi_e_firme_non_ammesse() -> None:
    p384 = ec.generate_private_key(ec.SECP384R1())
    assert not verifica(_der(p384), p384.sign(MSG, ec.ECDSA(hashes.SHA256())), MSG)
    rsa_k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert not verifica(_der(rsa_k), b"\0" * 256, MSG)
    assert not verifica(b"non una chiave", b"\0" * 64, MSG)
    p256 = ec.generate_private_key(ec.SECP256R1())
    assert not verifica(_der(p256), b"\0" * 10, MSG)
