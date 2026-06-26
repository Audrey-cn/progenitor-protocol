"""RSA signature hardening (docs/AKASHIC_LAYERED_ARCHITECTURE.md §5).

New identities sign with EMSA-PKCS1-v1_5 padding (rigid encoding → no textbook-RSA forgery), while
the legacy raw scheme stays verify-only so already-committed signatures keep verifying.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hatchery"))
import stargate_identity as si  # noqa: E402


def test_new_identity_uses_pkcs1_padding():
    ident = si.generate_identity("alice", bits=1024)
    assert ident["key_type"] == si.KEY_TYPE
    doc = si.sign_document({"msg": "hi"}, ident)
    assert doc["signature"]["algorithm"] == "rsa-pkcs1-sha256"
    assert doc["signature"]["key_type"] == si.KEY_TYPE
    assert si.verify_document(doc, ident["public_key"]) is True


def test_padded_signature_rejects_tamper():
    ident = si.generate_identity("bob", bits=1024)
    doc = si.sign_document({"msg": "original", "n": 1}, ident)
    doc["n"] = 2  # tamper a signed field
    assert si.verify_document(doc, ident["public_key"]) is False


def test_padding_actually_present_in_recovered_message():
    # the recovered EM must carry the 0x0001 FF.. 00 DigestInfo structure, not a bare digest
    ident = si.generate_identity("carol", bits=1024)
    doc = si.sign_document({"x": 1}, ident)
    actual, n = si._recovered_message(doc, ident["public_key"])
    em = actual.to_bytes(si._key_byte_len(n), "big")
    assert em[0:2] == b"\x00\x01"
    assert b"\xff\xff\xff\xff\xff\xff\xff\xff" in em       # 0xFF padding string
    assert si._SHA256_DIGESTINFO_PREFIX in em               # the SHA-256 DigestInfo binds the hash


def test_retired_raw_scheme_is_rejected():
    # the legacy unpadded scheme is gone — a signature claiming it must not verify (hard cutover)
    ident = si.generate_identity("x", bits=1024)
    doc = si.sign_document({"msg": "hi"}, ident)
    doc["signature"]["key_type"] = "progenitor-rsa-sha256-v1"  # the retired textbook scheme
    assert si.verify_document(doc, ident["public_key"]) is False
