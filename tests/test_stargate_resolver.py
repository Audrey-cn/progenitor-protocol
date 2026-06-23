import hashlib
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from urllib import request

REPO_DIR = Path(__file__).resolve().parent.parent
REGISTRY_DIR = REPO_DIR.parent / "progenitor-registry"
HATCHERY_DIR = REPO_DIR / "hatchery"
TOOLS_DIR = REPO_DIR / "tools"

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(HATCHERY_DIR))

import stargate_resolver
import engine
import stargate_identity


def test_index_v2_schema_has_transport_hints():
    index = stargate_resolver.normalize_index(stargate_resolver.load_index())
    assert index
    for name, entry in index.items():
        assert entry["schema_version"] == "akashic.index/v2"
        assert entry["capability"] == name
        assert len(entry["content_sha256"]) == 64
        assert entry["content_id"] == entry["content_sha256"]
        assert entry["registry_path"] == f"genes/{entry['content_sha256']}"
        assert entry["trust_state"] == "registry_verified"
        assert any(h["type"] == "registry_path" for h in entry["transport_hints"])
        assert any(h["type"] == "github_raw" for h in entry["transport_hints"])


def test_verify_index_and_resolve_local_payload():
    issues = stargate_resolver.verify_index(stargate_resolver.load_index())
    assert issues == []

    resolved = stargate_resolver.resolve_gene("code-reviewer")
    assert resolved.name == "code-reviewer"
    assert resolved.source.endswith(resolved.content_sha256)
    assert hashlib.sha256(resolved.payload).hexdigest() == resolved.content_sha256


def test_peer_manifest_shape_from_resolver():
    manifest = stargate_resolver.build_peer_manifest(stargate_resolver.load_index(), node_id="test-node")
    assert manifest["schema_version"] == "akashic.peer-manifest/v1"
    assert manifest["node_id"] == "test-node"
    assert manifest["genes"]
    first = manifest["genes"][0]
    assert "capability" in first
    assert "content_sha256" in first
    assert "transport_hints" in first


def test_local_gateway_manifest_records(tmp_path):
    gene_path = tmp_path / "gene.pgn"
    gene_payload = b"# life_id: PGN@L1-G99-PEER\n# creator: Test\n# description: peer manifest test\n"
    gene_path.write_bytes(gene_payload)
    expected = hashlib.sha256(gene_payload).hexdigest()

    gateway = engine.LocalGateway(port=18080)
    gateway.register_gene("peer-test", str(gene_path))
    record = gateway._gene_record("peer-test")

    assert record["capability"] == "peer-test"
    assert record["content_sha256"] == expected
    assert record["trust_state"] == "peer_advertised"
    assert record["transport_hints"][0]["type"] == "peer"
    assert any(h["type"] == "peer_hash" for h in record["transport_hints"])


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_identity_sign_and_verify_manifest():
    identity = stargate_identity.generate_identity("node-test", bits=1024)
    manifest = stargate_resolver.build_peer_manifest(
        {"demo": {"content_sha256": "a" * 64, "registry_path": "genes/" + "a" * 64}},
        identity=identity,
    )

    assert manifest["node_id"] == "node-test"
    assert manifest["signature"]["public_key_id"] == identity["public_key_id"]
    assert stargate_identity.verify_document(manifest, identity["public_key"])

    tampered = json.loads(json.dumps(manifest))
    tampered["genes"][0]["content_sha256"] = "b" * 64
    assert not stargate_identity.verify_document(tampered, identity["public_key"])


def test_peer_handshake_and_hash_resolve(tmp_path):
    gene_path = tmp_path / "peer_gene.pgn"
    payload = b"# life_id: PGN@L1-G100-HANDSHAKE\n# creator: Peer\n# description: signed handshake test\n"
    gene_path.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    port = _free_port()
    identity = stargate_identity.generate_identity(f"peer-node:{port}", bits=1024)

    gateway = engine.LocalGateway(port=port, identity=identity)
    gateway.register_gene("signed-peer-test", str(gene_path))
    thread = threading.Thread(target=gateway.start, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                with request.urlopen(f"{base_url}/hello", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except OSError:
                time.sleep(0.05)
        session = stargate_resolver.handshake_peer(base_url)
        assert session["manifest"]["node_id"] == f"peer-node:{port}"
        assert session["manifest"]["signature"]

        resolved = stargate_resolver.resolve_from_peer(base_url, "signed-peer-test")
        assert resolved.content_sha256 == expected
        assert resolved.payload == payload
        assert resolved.source.endswith(expected)
    finally:
        gateway.stop()


def test_peer_list_discovery_and_blocked_peer(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(stargate_resolver, "TRUST_DIR", runtime / "trust")
    monkeypatch.setattr(stargate_resolver, "TRUSTED_PEERS_FILE", runtime / "trust" / "trusted_peers.json")
    monkeypatch.setattr(stargate_resolver, "BLOCKED_PEERS_FILE", runtime / "trust" / "blocked_peers.json")
    monkeypatch.setattr(stargate_resolver, "PEER_LIST_FILE", runtime / "trust" / "peers.json")
    monkeypatch.setattr(stargate_resolver, "PEER_AUDIT_FILE", runtime / "trust" / "peer_audit_log.jsonl")

    gene_path = tmp_path / "discover_gene.pgn"
    payload = b"# life_id: PGN@L1-G102-DISCOVERY\n# creator: Peer\n# description: discovery test\n"
    gene_path.write_bytes(payload)
    port = _free_port()
    identity = stargate_identity.generate_identity(f"discover-node:{port}", bits=1024)

    gateway = engine.LocalGateway(port=port, identity=identity)
    gateway.register_gene("discover-peer-test", str(gene_path))
    thread = threading.Thread(target=gateway.start, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                with request.urlopen(f"{base_url}/hello", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except OSError:
                time.sleep(0.05)

        stargate_resolver.add_peer(base_url, label="test")
        discovered = stargate_resolver.discover_peers()
        assert discovered["peers"][0]["status"] == "ok"
        assert discovered["peers"][0]["genes"] == 1

        stargate_resolver.block_peer(base_url, reason="test-block")
        try:
            stargate_resolver.handshake_peer(base_url)
            assert False, "blocked peer should be rejected"
        except PermissionError:
            pass
    finally:
        gateway.stop()


def test_legacy_index_entry_still_normalizes():
    normalized = stargate_resolver.normalize_entry("legacy", "c" * 64)
    assert normalized["schema_version"] == "akashic.index/v2"
    assert normalized["capability"] == "legacy"
    assert normalized["content_sha256"] == "c" * 64
    assert normalized["registry_path"] == "genes/" + "c" * 64


def test_udp_beacon_scan_registers_candidate_peer(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(stargate_resolver, "TRUST_DIR", runtime / "trust")
    monkeypatch.setattr(stargate_resolver, "TRUSTED_PEERS_FILE", runtime / "trust" / "trusted_peers.json")
    monkeypatch.setattr(stargate_resolver, "BLOCKED_PEERS_FILE", runtime / "trust" / "blocked_peers.json")
    monkeypatch.setattr(stargate_resolver, "PEER_LIST_FILE", runtime / "trust" / "peers.json")
    monkeypatch.setattr(stargate_resolver, "PEER_AUDIT_FILE", runtime / "trust" / "peer_audit_log.jsonl")

    udp_port = _free_port()
    gateway_port = _free_port()
    beacon = engine.PassiveBeacon(port=udp_port, gateway_port=gateway_port, node_id="beacon-node")
    beacon.update_manifest([{"capability": "beacon-test", "content_sha256": "d" * 64}])
    try:
        assert beacon.start()["status"] == "beacon_started"
        result = {"peers": []}
        for _ in range(20):
            result = stargate_resolver.beacon_scan(timeout=0.2, udp_port=udp_port, target_host="127.0.0.1")
            if result["peers"]:
                break
            time.sleep(0.05)
        assert result["peers"]
        peer = result["peers"][0]
        assert peer["peer_url"] == f"http://127.0.0.1:{gateway_port}"
        assert peer["node_id"] == "beacon-node"
        assert stargate_resolver.list_peers()[0]["peer_url"] == peer["peer_url"]
    finally:
        beacon.stop()


def test_peer_sync_imports_known_peers_from_signed_manifest(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(stargate_resolver, "TRUST_DIR", runtime / "trust")
    monkeypatch.setattr(stargate_resolver, "TRUSTED_PEERS_FILE", runtime / "trust" / "trusted_peers.json")
    monkeypatch.setattr(stargate_resolver, "BLOCKED_PEERS_FILE", runtime / "trust" / "blocked_peers.json")
    monkeypatch.setattr(stargate_resolver, "PEER_LIST_FILE", runtime / "trust" / "peers.json")
    monkeypatch.setattr(stargate_resolver, "PEER_AUDIT_FILE", runtime / "trust" / "peer_audit_log.jsonl")

    gene_path = tmp_path / "gossip_gene.pgn"
    gene_path.write_bytes(b"# life_id: PGN@L1-G104-GOSSIP\n# creator: Peer\n# description: gossip test\n")
    port = _free_port()
    advertised_peer = "http://127.0.0.1:65530"
    identity = stargate_identity.generate_identity(f"gossip-node:{port}", bits=1024)
    gateway = engine.LocalGateway(port=port, identity=identity)
    gateway.register_gene("gossip-test", str(gene_path))
    gateway.register_peer(advertised_peer, label="relay-candidate")
    thread = threading.Thread(target=gateway.start, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                with request.urlopen(f"{base_url}/hello", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except OSError:
                time.sleep(0.05)
        stargate_resolver.add_peer(base_url, label="seed")
        synced = stargate_resolver.sync_peers()
        assert synced["peers"][0]["status"] == "ok"
        assert synced["peers"][0]["imported_peers"] == 1
        assert any(peer["peer_url"] == advertised_peer for peer in stargate_resolver.list_peers())
    finally:
        gateway.stop()


def test_bootstrap_import_supports_file_and_legacy_strings(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(stargate_resolver, "TRUST_DIR", runtime / "trust")
    monkeypatch.setattr(stargate_resolver, "TRUSTED_PEERS_FILE", runtime / "trust" / "trusted_peers.json")
    monkeypatch.setattr(stargate_resolver, "BLOCKED_PEERS_FILE", runtime / "trust" / "blocked_peers.json")
    monkeypatch.setattr(stargate_resolver, "PEER_LIST_FILE", runtime / "trust" / "peers.json")
    monkeypatch.setattr(stargate_resolver, "PEER_AUDIT_FILE", runtime / "trust" / "peer_audit_log.jsonl")

    bootstrap = tmp_path / "peers.json"
    bootstrap.write_text(json.dumps({
        "schema_version": "akashic.bootstrap/v1",
        "peers": [
            "http://127.0.0.1:60001",
            {"peer_url": "http://127.0.0.1:60002", "label": "relay"},
            {"url": "not-a-url"},
        ],
    }), encoding="utf-8")

    result = stargate_resolver.import_bootstrap(str(bootstrap))
    assert result["count"] == 2
    peers = stargate_resolver.list_peers()
    assert {peer["peer_url"] for peer in peers} == {"http://127.0.0.1:60001", "http://127.0.0.1:60002"}


# ── [P0] Index signature verification ──────────────────────────────────────


def test_index_signature_valid():
    """A well-formed, correctly-signed index passes signature verification."""
    sig_issues = stargate_resolver.verify_index_signature()
    assert sig_issues == []


def test_index_signature_missing_sig(tmp_path):
    """Missing .sig file produces an error issue."""
    index = tmp_path / "unsigned.json"
    index.write_text(json.dumps({"key": "value"}), encoding="utf-8")
    issues = stargate_resolver.verify_index_signature(index_path=index)
    assert len(issues) == 1
    assert "signature file missing" in issues[0]["reason"]


def test_index_signature_tampered_index(tmp_path):
    """When index content changes but sig stays the same, verification fails."""
    original = stargate_resolver.INDEX_FILE.read_bytes()
    original_sig = stargate_resolver.INDEX_FILE.with_suffix(
        stargate_resolver.INDEX_FILE.suffix + ".sig"
    ).read_text(encoding="utf-8")

    # Copy index + sig to tmp
    index = tmp_path / ".akashic_index.json"
    sig = tmp_path / ".akashic_index.json.sig"
    index.write_bytes(original)
    sig.write_text(original_sig, encoding="utf-8")

    # Tamper the index content
    tampered_content = json.loads(index.read_text(encoding="utf-8"))
    tampered_content["evil-key"] = {"cid": "evil", "expected_sha256": "e" * 64}
    index.write_text(json.dumps(tampered_content, ensure_ascii=False), encoding="utf-8")

    issues = stargate_resolver.verify_index_signature(index_path=index)
    assert len(issues) == 1
    assert "index_sha256 mismatch" in issues[0]["reason"]


def test_index_signature_wrong_key(monkeypatch):
    """A different public key cannot verify the signature."""
    wrong_key = json.dumps({
        "key_type": "progenitor-rsa-sha256-v1",
        "n": "a" * 128,  # completely wrong key
        "e": 65537,
    })
    monkeypatch.setenv("PROGENITOR_REGISTRY_PUBLIC_KEY", wrong_key)
    issues = stargate_resolver.verify_index_signature()
    assert len(issues) == 1
    assert "cryptographic signature invalid" in issues[0]["reason"]


def test_index_signature_bad_envelope(tmp_path):
    """A .sig file that isn't valid JSON produces an error."""
    index = tmp_path / "idx.json"
    sig = tmp_path / "idx.json.sig"
    index.write_text("{}", encoding="utf-8")
    sig.write_text("not valid json {{{", encoding="utf-8")
    issues = stargate_resolver.verify_index_signature(index_path=index)
    assert len(issues) == 1
    assert "sig read error" in issues[0]["reason"]


def test_index_signature_verify_index_integration():
    """verify_index() plus verify_index_signature() together catch all issues."""
    from stargate_resolver import normalize_index, load_index, verify_index, verify_index_signature

    index = normalize_index(load_index())
    issues = verify_index(index)
    sig_issues = verify_index_signature()
    all_issues = issues + sig_issues
    # With the valid .sig, there should be no sig issues
    assert sig_issues == []
    # Content issues should also be 0 for a well-formed registry
    assert all(i["level"] != "error" or "signature" in i.get("reason", "") for i in all_issues) or len(all_issues) == 0


def test_verify_index_signature_load_public_key():
    """Default public key is valid and loadable."""
    pk = stargate_resolver.load_registry_public_key()
    assert pk is not None
    assert pk["key_type"] == "progenitor-rsa-sha256-v1"
    assert "n" in pk
    assert "e" in pk
    assert pk["e"] == 65537
