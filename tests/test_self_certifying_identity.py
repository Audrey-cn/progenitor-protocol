"""Self-certifying node identity (docs/AKASHIC_LAYERED_ARCHITECTURE.md §4).

node_id MUST equal the public-key fingerprint, so a node id is an unforgeable claim — the keystone
that unblocks the peer handshake. These tests prove the binding holds and that forged ids are
rejected both at the unit level (verify_node_identity) and at the handshake gate.
"""
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "tools"))
sys.path.insert(0, str(REPO_DIR / "hatchery"))

import stargate_identity as si  # noqa: E402
import stargate_resolver as sr  # noqa: E402


def test_generated_node_id_is_the_key_fingerprint():
    ident = si.generate_identity("alice-laptop", bits=512)
    assert ident["node_id"] == ident["public_key_id"]
    assert ident["node_id"] == si.derive_node_id(ident["public_key"])
    # the human name lives in label, never in the authoritative node_id
    assert ident["label"] == "alice-laptop"


def test_verify_node_identity_accepts_genuine_public_identity():
    ident = si.generate_identity("bob", bits=512)
    assert si.verify_node_identity(si.public_identity(ident)) is True


def test_verify_rejects_forged_node_id():
    # attacker keeps a valid key but claims someone else's id
    node = si.public_identity(si.generate_identity("attacker", bits=512))
    node["node_id"] = si.derive_node_id(si.generate_identity("victim", bits=512)["public_key"])
    assert si.verify_node_identity(node) is False


def test_verify_rejects_forged_public_key_id():
    # attacker advertises a fingerprint that does not match the advertised key
    node = si.public_identity(si.generate_identity("attacker", bits=512))
    node["public_key_id"] = "0" * 64
    node["node_id"] = "0" * 64
    assert si.verify_node_identity(node) is False


def test_verify_rejects_missing_key():
    assert si.verify_node_identity({"node_id": "x", "public_key_id": "x"}) is False


def test_handshake_rejects_non_self_certifying_peer(monkeypatch):
    # a peer whose /hello advertises an arbitrary (legacy, forgeable) node_id is refused before
    # any manifest fetch — the gate that unblocks safe peering.
    legacy_node = si.public_identity(si.generate_identity("legacy", bits=512))
    legacy_node["node_id"] = "local-gateway:9999"  # not the fingerprint
    hello = {
        "schema_version": sr.HELLO_VERSION,
        "protocol_versions": {"peer_manifest": [sr.PEER_MANIFEST_VERSION]},
        "node": legacy_node,
    }
    monkeypatch.setattr(sr, "fetch_json", lambda url, timeout=10: hello)
    monkeypatch.setattr(sr, "is_blocked_peer", lambda peer_url, node_id="": False)
    monkeypatch.setattr(sr, "audit_peer", lambda *a, **k: None)
    try:
        sr.handshake_peer("http://127.0.0.1:1")
        assert False, "non-self-certifying peer must be rejected"
    except ValueError as exc:
        assert "self-certifying" in str(exc)


def test_handshake_rejects_beacon_id_mismatch(monkeypatch):
    # a beacon claimed one node_id; the peer's verified (self-certifying) id is different → reject.
    node = si.public_identity(si.generate_identity("honest", bits=512))
    hello = {
        "schema_version": sr.HELLO_VERSION,
        "protocol_versions": {"peer_manifest": [sr.PEER_MANIFEST_VERSION]},
        "node": node,
    }
    monkeypatch.setattr(sr, "fetch_json", lambda url, timeout=10: hello)
    monkeypatch.setattr(sr, "is_blocked_peer", lambda peer_url, node_id="": False)
    monkeypatch.setattr(sr, "audit_peer", lambda *a, **k: None)
    try:
        sr.handshake_peer("http://127.0.0.1:1", expected_node_id="f" * 64)
        assert False, "a beacon id that doesn't match the verified key must be rejected"
    except ValueError as exc:
        assert "beacon-advertised" in str(exc)
