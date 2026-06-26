import hashlib
import socket
import sys
import threading
import time
from pathlib import Path
from urllib import request

from conftest import clean_test_data

REPO_DIR = Path(__file__).resolve().parent.parent
HATCHERY_DIR = REPO_DIR / "hatchery"
TOOLS_DIR = REPO_DIR / "tools"

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(HATCHERY_DIR))

import engine
import stargate_identity
import stargate_resolver


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_http(url: str):
    for _ in range(50):
        try:
            with request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"server did not become ready: {url}")


def test_passive_beacon_ack_uses_actual_gateway_port(tmp_path):
    udp_port = _free_port()
    gateway_port = _free_port()
    beacon = engine.PassiveBeacon(port=udp_port, gateway_port=gateway_port, node_id="p2p-beacon")
    beacon.update_manifest([{"capability": "beacon-gene", "content_sha256": "a" * 64}])
    try:
        assert beacon.start()["status"] == "beacon_started"
        result = {"peers": []}
        for _ in range(20):
            result = stargate_resolver.beacon_scan(timeout=0.2, udp_port=udp_port, target_host="127.0.0.1", register=False)
            if result["peers"]:
                break
            time.sleep(0.05)
        assert result["peers"]
        assert result["peers"][0]["peer_url"] == f"http://127.0.0.1:{gateway_port}"
        assert result["peers"][0]["node_id"] == "p2p-beacon"
    finally:
        beacon.stop()


def test_beacon_discovery_marks_id_unverified(tmp_path):
    udp_port = _free_port()
    gateway_port = _free_port()
    beacon = engine.PassiveBeacon(port=udp_port, gateway_port=gateway_port, node_id="claimed-id")
    try:
        assert beacon.start()["status"] == "beacon_started"
        result = {"peers": []}
        for _ in range(20):
            result = stargate_resolver.beacon_scan(timeout=0.2, udp_port=udp_port, target_host="127.0.0.1", register=False)
            if result["peers"]:
                break
            time.sleep(0.05)
        assert result["peers"]
        # a beacon node_id is only a claim until the signed handshake binds it
        assert result["peers"][0]["id_verified"] is False
    finally:
        beacon.stop()


def test_handshake_binds_beacon_claimed_id(tmp_path):
    gene_path = tmp_path / "bind_gene.pgn"
    gene_path.write_bytes(b"# life_id: PGN@L1-G111-BIND\n# creator: Peer\n")
    port = _free_port()
    identity = stargate_identity.generate_identity(f"bind-node:{port}", bits=1024)
    gateway = engine.LocalGateway(port=port, identity=identity)
    gateway.register_gene("bind-test", str(gene_path))
    threading.Thread(target=gateway.start, daemon=True).start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_http(f"{base_url}/hello")
        # correct claim (the real fingerprint) → handshake succeeds
        ok = stargate_resolver.handshake_peer(base_url, expected_node_id=identity["node_id"])
        assert ok["manifest"]["node_id"] == identity["node_id"]
        # forged claim → handshake refuses, binding the discovery id to the verified key
        try:
            stargate_resolver.handshake_peer(base_url, expected_node_id="b" * 64)
            assert False, "forged beacon id must be rejected at handshake"
        except ValueError as exc:
            assert "beacon-advertised" in str(exc)
    finally:
        gateway.stop()


def test_manifest_advertises_ledger_reputation(tmp_path):
    import evolution
    gene_path = tmp_path / "rep_gene.pgn"
    gene_path.write_bytes(b"# life_id: PGN@L1-G112-REP\n# creator: Peer\n")
    expected = hashlib.sha256(gene_path.read_bytes()).hexdigest()
    port = _free_port()
    identity = stargate_identity.generate_identity(f"rep-node:{port}", bits=1024)
    gateway = engine.LocalGateway(port=port, identity=identity)
    gateway.ledger = evolution.GeneLedger()
    gateway.ledger.register_version("rep-test", expected)
    gateway.ledger.record_outcome(expected, success=True)
    gateway.ledger.record_outcome(expected, success=True)
    gateway.register_gene("rep-test", str(gene_path))
    threading.Thread(target=gateway.start, daemon=True).start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_http(f"{base_url}/hello")
        session = stargate_resolver.handshake_peer(base_url)
        entry = next(g for g in session["manifest"]["genes"] if g["content_sha256"] == expected)
        # the peer's first-hand L4 evidence rode along on the signed manifest
        assert entry["reputation"] == 2.0
        assert entry["lineage_depth"] == 2
        assert entry["retired"] is False
    finally:
        gateway.stop()


def test_gateway_manifest_and_gene_hash_endpoints(tmp_path):
    gene_path = tmp_path / "p2p_gene.pgn"
    payload = b"# life_id: PGN@L1-G105-P2P\n# creator: Peer\n# description: p2p connectivity test\n"
    gene_path.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    port = _free_port()
    identity = stargate_identity.generate_identity(f"p2p-node:{port}", bits=1024)

    gateway = engine.LocalGateway(port=port, identity=identity)
    gateway.register_gene("p2p-hash-test", str(gene_path))
    thread = threading.Thread(target=gateway.start, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_http(f"{base_url}/hello")
        session = stargate_resolver.handshake_peer(base_url)
        assert session["manifest"]["signature"]
        assert session["manifest"]["genes"][0]["content_sha256"] == expected

        resolved = stargate_resolver.resolve_from_peer(base_url, expected)
        assert resolved.payload == payload
        assert resolved.content_sha256 == expected
    finally:
        gateway.stop()


def test_legacy_peer_pull_requires_hash_when_expected(tmp_path):
    gene_path = tmp_path / "legacy_peer_gene.pgn"
    payload = b"# life_id: PGN@L1-G106-LEGACY-PULL\n# creator: Peer\n# description: legacy pull hash guard\n"
    gene_path.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    port = _free_port()
    identity = stargate_identity.generate_identity(f"legacy-peer:{port}", bits=1024)

    gateway = engine.LocalGateway(port=port, identity=identity)
    gateway.register_gene("legacy-pull-test", str(gene_path))
    thread = threading.Thread(target=gateway.start, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_http(f"{base_url}/hello")
        assert engine.phagocytize_from_peer("legacy-pull-test", base_url, expected_sha256=expected) == payload
        try:
            engine.phagocytize_from_peer("legacy-pull-test", base_url, expected_sha256="b" * 64)
            assert False, "hash mismatch must fail"
        except (RuntimeError, ValueError):
            pass
    finally:
        gateway.stop()


def test_akashic_phagocytize_prefers_content_sha256_api(tmp_path, monkeypatch):
    payload = b"# life_id: PGN@L1-G107-CONTENT-API\n# creator: Test\n# description: content api\n"
    expected = hashlib.sha256(payload).hexdigest()
    captured = {}

    def fake_pull(transport):
        captured["transport"] = transport
        return payload

    def fake_land(raw_data, content_id):
        path = tmp_path / "landed_gene.pgn"
        path.write_bytes(raw_data)
        captured["landed_content_id"] = content_id
        return str(path)

    def fake_audit(filepath, expected_sha256=None):
        captured["expected_sha256"] = expected_sha256
        return True

    monkeypatch.setattr(engine, "_pull_via_transport_hint", fake_pull)
    monkeypatch.setattr(engine, "_land_content_before_ingest", fake_land)
    monkeypatch.setattr(engine, "crucible_audit", fake_audit)

    result = engine.akashic_phagocytize(content_sha256=expected, transport_hint="local://gene")
    assert "local://gene" in result
    assert captured["transport"] == "local://gene"
    assert captured["landed_content_id"] == "local://gene"
    assert captured["expected_sha256"] == expected


def test_akashic_receptor_rejects_legacy_gene_cid_alias(tmp_path, monkeypatch):
    payload = b"# life_id: PGN@L1-G108-LEGACY-CID\n# creator: Test\n# description: legacy alias removed\n"
    captured = {}

    def fake_pull(transport):
        captured["transport"] = transport
        return payload

    monkeypatch.setattr(engine, "_pull_via_transport_hint", fake_pull)
    monkeypatch.setattr(engine, "_land_content_before_ingest", lambda raw_data, content_id: str(tmp_path / "legacy_gene.pgn"))
    monkeypatch.setattr(engine, "crucible_audit", lambda filepath, expected_sha256=None: captured.setdefault("expected_sha256", expected_sha256) is None)

    receptor = engine.AkashicReceptor()
    try:
        receptor.phagocytize_gene(gene_cid="legacy-cid")
        assert False, "legacy alias should be removed"
    except TypeError:
        pass


def test_akashic_tool_schemas_expose_content_addressed_api():
    expected = {"content_sha256", "capability_name", "transport_hint"}

    receptor_props = set(engine.AKASHIC_TOOL_SCHEMA["function"]["parameters"]["properties"])
    phagocyte_props = set(engine.Phagocyte.AKASHIC_TOOL_SCHEMA["function"]["parameters"]["properties"])

    assert receptor_props == expected
    assert phagocyte_props == expected


def test_internal_content_transport_wrappers_keep_legacy_implementation(monkeypatch):
    captured = {}

    def fake_legacy_pull(value):
        captured["pull"] = value
        return b"payload"

    def fake_legacy_land(raw_data, value):
        captured["land"] = (raw_data, value)
        return "landed"

    monkeypatch.setattr(engine, "_transmembrane_pull", fake_legacy_pull)
    monkeypatch.setattr(engine, "_local_write_before_ingest", fake_legacy_land)

    assert engine._pull_via_transport_hint("transport://gene") == b"payload"
    assert engine._land_content_before_ingest(b"payload", "content-id") == "landed"
    assert captured["pull"] == "transport://gene"
    assert captured["land"] == (b"payload", "content-id")


def test_spore_daemon_kubo_detection_uses_transport_probe(monkeypatch):
    captured = {}

    def fake_probe(url):
        captured["url"] = url
        return True

    monkeypatch.setattr(engine.stargate_transport, "probe_kubo_alive", fake_probe)

    assert engine.SporeDaemon()._is_kubo_running() is True
    assert captured["url"] == engine.KUBO_API_URL


def test_signature_required_mode_fails_closed_for_external_missing_signature(tmp_path, monkeypatch):
    gene_path = tmp_path / "unsigned_external_gene.pgn"
    gene_path.write_text("# life_id: PGN@L1-G110-SIG\n", encoding="utf-8")

    monkeypatch.setattr(engine, "SIGNER_FINGERPRINTS", ["ABCDEF"])
    monkeypatch.setattr(engine, "SIGNATURE_MODE", "required")
    monkeypatch.setattr(engine, "SIGNATURE_REQUIRED", True)

    assert engine._verify_digital_signature(str(gene_path), is_internal=False) is False


def test_early_phagocyte_uses_unified_transport_and_landing(monkeypatch):
    captured = {}

    def fake_pull(value):
        captured["pull"] = value
        return b"payload"

    def fake_land(raw_data, value):
        captured["land"] = (raw_data, value)
        return "landed"

    monkeypatch.setattr(engine, "_pull_via_transport_hint", fake_pull)
    monkeypatch.setattr(engine, "_land_content_before_ingest", fake_land)

    phagocyte = engine.Phagocyte()
    assert phagocyte._gateway_fetch("transport://old") == b"payload"
    assert phagocyte._lysosome_land(b"payload", "content-id") == "landed"
    assert captured["pull"] == "transport://old"
    assert captured["land"] == (b"payload", "content-id")


def test_early_phagocyte_content_api_executes_without_legacy_aliases(tmp_path, monkeypatch):
    payload = b"# life_id: PGN@L1-G109-EARLY-CONTENT\n# creator: Test\n# description: early content api\n"
    expected = hashlib.sha256(payload).hexdigest()
    captured = {}

    def fake_fetch(transport):
        captured["transport"] = transport
        return payload

    def fake_land(raw_data, content_id):
        captured["land"] = (raw_data, content_id)
        path = tmp_path / "early_content_gene.pgn"
        path.write_bytes(raw_data)
        return str(path)

    def fake_audit(filepath, expected_sha256=None):
        captured["expected_sha256"] = expected_sha256
        return True

    monkeypatch.setattr(engine.Phagocyte, "_gateway_fetch", staticmethod(fake_fetch))
    monkeypatch.setattr(engine.Phagocyte, "_lysosome_land", staticmethod(fake_land))
    monkeypatch.setattr(engine.Phagocyte, "_crucible_remote", staticmethod(fake_audit))

    result = engine.Phagocyte().phagocytize_gene(content_sha256=expected, transport_hint="peer://gene")

    assert "peer://gene" in result
    assert captured["transport"] == "peer://gene"
    assert captured["land"] == (payload, "peer://gene")
    assert captured["expected_sha256"] == expected


def teardown_module():
    clean_test_data()
