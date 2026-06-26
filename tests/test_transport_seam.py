"""Transport & identity sidecar seams (docs/AKASHIC_LAYERED_ARCHITECTURE.md §5).

These prove a NEW transport / signature scheme plugs in by registration alone — no edit to
resolve_transport, verify_document, or any upper layer — which is what keeps the zero-dependency
core intact while allowing an optional libp2p/IPFS/Syncthing-relay or Ed25519 sidecar.
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hatchery"))
import transport  # noqa: E402
import stargate_identity as si  # noqa: E402


def test_registered_transport_is_dispatched_and_hash_verified():
    payload = b"gene-bytes-from-a-sidecar-transport"
    digest = hashlib.sha256(payload).hexdigest()

    registry = transport.default_registry()
    # a fictional sidecar transport — e.g. what a libp2p adapter would register
    registry.register("libp2p", lambda hint: payload if hint.get("url") == "peer-id-xyz" else None)
    assert "libp2p" in registry.types()

    hints = [{"type": "libp2p", "url": "peer-id-xyz", "priority": 10}]
    result = transport.resolve_transport(hints, digest, registry.fetcher())
    assert result["status"] == "fetched"
    assert result["transport"] == "libp2p"
    assert result["bytes"] == payload


def test_registered_transport_still_fails_closed_on_hash_mismatch():
    registry = transport.default_registry()
    registry.register("libp2p", lambda hint: b"tampered")
    hints = [{"type": "libp2p", "url": "x"}]
    result = transport.resolve_transport(hints, hashlib.sha256(b"original").hexdigest(), registry.fetcher())
    assert result["status"] == "exhausted"
    assert result["bytes"] is None


def test_default_fetcher_behaviour_unchanged(tmp_path):
    # the back-compat wrapper still routes file hints exactly as before
    blob = b"local-gene"
    digest = hashlib.sha256(blob).hexdigest()
    (tmp_path / digest).write_bytes(blob)
    fetcher = transport.default_fetcher(base_dir=str(tmp_path))
    result = transport.resolve_transport([{"type": "registry_path", "url": digest}], digest, fetcher)
    assert result["bytes"] == blob


def test_registered_signature_scheme_is_dispatched():
    doc = {"payload": "hello", "signature": {"key_type": "fake-scheme-v1", "value": "ok"}}

    def fake_verify(document, key):
        return document["signature"]["value"] == "ok" and key.get("k") == "pub"

    si.register_signature_scheme("fake-scheme-v1", fake_verify)
    assert si.verify_document(doc, {"k": "pub"}) is True
    # tamper the value → the registered scheme rejects it
    doc["signature"]["value"] = "no"
    assert si.verify_document(doc, {"k": "pub"}) is False


def test_unknown_signature_scheme_is_rejected():
    doc = {"payload": "x", "signature": {"key_type": "never-registered", "value": "v"}}
    assert si.verify_document(doc, {"k": "pub"}) is False
