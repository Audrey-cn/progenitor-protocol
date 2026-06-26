from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from pathlib import Path


KEY_TYPE = "progenitor-rsa-pkcs1-sha256-v1"  # the one signature scheme: EMSA-PKCS1-v1_5 padded RSA-SHA256
DEFAULT_E = 65537
DEFAULT_KEY_BITS = 2048  # modern minimum; pure-Python keygen is one-time and cached per node

# ASN.1 DER DigestInfo prefix for SHA-256 (RFC 8017 §9.2) — what makes a PKCS#1 v1.5 signature bind
# to *this* hash algorithm. Its absence is exactly the textbook-RSA forgery surface we are closing.
_SHA256_DIGESTINFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def canonical_json(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64u(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def int_to_b64u(value: int) -> str:
    size = max(1, (value.bit_length() + 7) // 8)
    return b64u(value.to_bytes(size, "big"))


def b64u_to_int(value: str) -> int:
    return int.from_bytes(unb64u(value), "big")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _key_byte_len(n: int) -> int:
    return (n.bit_length() + 7) // 8


def _emsa_pkcs1_v15(message_digest: bytes, key_byte_len: int) -> int:
    """EMSA-PKCS1-v1_5 encode a SHA-256 digest to an integer < n (RFC 8017 §9.2).

    EM = 0x00 || 0x01 || PS(0xFF…) || 0x00 || DigestInfo(SHA-256) || H. The 0xFF padding and the
    DigestInfo make the encoded message rigid, so an attacker cannot multiplicatively forge a valid
    signature the way they can against raw ``pow(digest, d, n)``.
    """
    t = _SHA256_DIGESTINFO_PREFIX + message_digest
    ps_len = key_byte_len - len(t) - 3
    if ps_len < 8:
        raise ValueError("RSA key too small for a PKCS#1 v1.5 SHA-256 signature")
    em = b"\x00\x01" + (b"\xff" * ps_len) + b"\x00" + t
    return int.from_bytes(em, "big")


def _is_probable_prime(n: int, rounds: int = 16) -> bool:
    if n < 2:
        return False
    small_primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    if n in small_primes:
        return True
    if any(n % p == 0 for p in small_primes):
        return False

    d = n - 1
    s = 0
    while d % 2 == 0:
        s += 1
        d //= 2

    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _generate_prime(bits: int) -> int:
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(candidate):
            return candidate


def derive_node_id(public_key: dict) -> str:
    """The self-certifying node id = fingerprint of the canonical public key (== ``public_key_id``).

    Mirrors a Syncthing Device ID / libp2p PeerID: the id *is* the key fingerprint, so a node id is
    an unforgeable claim — you cannot present an id without holding the matching private key (proven
    separately by a signature). This is what lets the peer mesh bind names to keys with no central
    authority. Human-friendly names live in the non-authoritative ``label`` field, never ``node_id``.
    """
    return sha256_hex(canonical_json(public_key))


def generate_identity(label: str = "", bits: int = DEFAULT_KEY_BITS) -> dict:
    half = bits // 2
    while True:
        p = _generate_prime(half)
        q = _generate_prime(half)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        if phi % DEFAULT_E != 0:
            break
    n = p * q
    d = pow(DEFAULT_E, -1, phi)
    public_key = {"key_type": KEY_TYPE, "n": int_to_b64u(n), "e": DEFAULT_E}
    public_key_id = derive_node_id(public_key)
    return {
        "schema_version": "akashic.node-identity/v1",
        "node_id": public_key_id,  # self-certifying: node_id IS the key fingerprint
        "label": label,
        "key_type": KEY_TYPE,
        "public_key": public_key,
        "public_key_id": public_key_id,
        "private_key": {"d": int_to_b64u(d)},
    }


def verify_node_identity(node: dict) -> bool:
    """A node descriptor is self-certifying iff its advertised fingerprint matches its key AND its
    ``node_id`` *is* that fingerprint. This does NOT prove key possession — a signature check
    (``verify_document``) proves that — but it makes the node id unforgeable: an impostor cannot
    advertise someone else's id without also advertising their public key, and then the signature
    check fails because the impostor lacks the private key.
    """
    public_key = node.get("public_key")
    if not public_key:
        return False
    fingerprint = derive_node_id(public_key)
    return node.get("public_key_id") == fingerprint and node.get("node_id") == fingerprint


def load_or_create_identity(path: Path, label: str = "", bits: int = 1024) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    identity = generate_identity(label, bits=bits)
    path.write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return identity


def public_identity(identity: dict) -> dict:
    return {
        "schema_version": identity.get("schema_version", "akashic.node-identity/v1"),
        "node_id": identity["node_id"],
        "label": identity.get("label", ""),
        "key_type": identity.get("key_type", KEY_TYPE),
        "public_key": identity["public_key"],
        "public_key_id": identity["public_key_id"],
    }


def signature_payload(document: dict) -> dict:
    return {k: v for k, v in document.items() if k != "signature"}


def sign_document(document: dict, identity: dict) -> dict:
    """Sign a document with EMSA-PKCS1-v1_5 padded RSA-SHA256 (the one scheme)."""
    payload = signature_payload(document)
    digest = hashlib.sha256(canonical_json(payload)).digest()
    n = b64u_to_int(identity["public_key"]["n"])
    d = b64u_to_int(identity["private_key"]["d"])
    signed = dict(payload)
    signed["signature"] = {
        "schema_version": "akashic.signature/v1",
        "key_type": KEY_TYPE,
        "public_key_id": identity["public_key_id"],
        "algorithm": "rsa-pkcs1-sha256",
        "value": int_to_b64u(pow(_emsa_pkcs1_v15(digest, _key_byte_len(n)), d, n)),
    }
    return signed


def _recovered_message(document: dict, key: dict):
    signature = document.get("signature") or {}
    try:
        n = b64u_to_int(key["n"])
        e = int(key["e"])
        return pow(b64u_to_int(signature.get("value", "")), e, n), n
    except (KeyError, ValueError, TypeError):
        return None, None


def _verify_rsa_pkcs1_sha256(document: dict, key: dict) -> bool:
    actual, n = _recovered_message(document, key)
    if actual is None:
        return False
    try:
        expected = _emsa_pkcs1_v15(
            hashlib.sha256(canonical_json(signature_payload(document))).digest(), _key_byte_len(n))
    except ValueError:
        return False
    return actual == expected


# Signature-scheme seam (docs/AKASHIC_LAYERED_ARCHITECTURE.md §5): verify_document dispatches by the
# signature's declared key_type, so an Ed25519 (or any external-crypto) scheme plugs in by
# registration without touching callers. Exactly one scheme ships — the padded PKCS#1 RSA-SHA256.
# Any other (including the retired textbook-RSA "progenitor-rsa-sha256-v1") fails to verify.
_SIGNATURE_VERIFIERS = {KEY_TYPE: _verify_rsa_pkcs1_sha256}


def register_signature_scheme(key_type: str, verify_fn) -> None:
    """Register a verifier ``verify_fn(document, public_key) -> bool`` for a signature ``key_type``."""
    _SIGNATURE_VERIFIERS[key_type] = verify_fn


def verify_document(document: dict, public_key: dict | None = None) -> bool:
    signature = document.get("signature") or {}
    key = public_key or document.get("public_key")
    if not key:
        return False
    verifier = _SIGNATURE_VERIFIERS.get(signature.get("key_type"))
    if verifier is None:
        return False
    return verifier(document, key)


def default_identity_path(port: int | str = "local") -> Path:
    runtime = Path(os.environ.get("PROGENITOR_RUNTIME_DIR", Path.cwd() / ".progenitor_runtime"))
    return runtime / "identity" / f"node_{port}.json"
