from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request

from repo_paths import PROTOCOL_DIR, REGISTRY_DIR, REPORT_DIR, RUNTIME_DIR

HATCHERY_DIR = PROTOCOL_DIR / "hatchery"
if str(HATCHERY_DIR) not in sys.path:
    sys.path.insert(0, str(HATCHERY_DIR))

from stargate_identity import sign_document, verify_document, verify_node_identity

INDEX_FILE = REGISTRY_DIR / ".akashic_index.json"
GENES_DIR = REGISTRY_DIR / "genes"
TRUST_DIR = RUNTIME_DIR / "trust"
TRUSTED_PEERS_FILE = TRUST_DIR / "trusted_peers.json"
BLOCKED_PEERS_FILE = TRUST_DIR / "blocked_peers.json"
PEER_LIST_FILE = TRUST_DIR / "peers.json"
PEER_AUDIT_FILE = TRUST_DIR / "peer_audit_log.jsonl"
DEFAULT_RAW_BASE = os.environ.get(
    "PROGENITOR_REGISTRY_RAW_BASE",
    "https://raw.githubusercontent.com/Audrey-cn/progenitor-registry/main",
)
SCHEMA_VERSION = "akashic.index/v2"
HELLO_VERSION = "akashic.hello/v1"
PEER_MANIFEST_VERSION = "akashic.peer-manifest/v1"
GENE_TRANSFER_VERSION = "akashic.gene-transfer/v1"
PEER_EXCHANGE_VERSION = "akashic.peer-exchange/v1"
BEACON_MESSAGE = b"PROGENITOR_DISCOVER"
DEFAULT_BEACON_PORT = 9999


@dataclass
class ResolvedGene:
    name: str
    content_sha256: str
    source: str
    payload: bytes
    entry: dict


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_index(path: Path = INDEX_FILE) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_json_file(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json_file(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def audit_peer(event: str, peer_url: str, detail: dict) -> None:
    TRUST_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"event": event, "peer_url": peer_url, "detail": detail}
    with PEER_AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def is_blocked_peer(peer_url: str, node_id: str = "") -> bool:
    blocked = load_json_file(BLOCKED_PEERS_FILE, {"peers": []})
    keys = {peer_url.rstrip("/"), node_id}
    return any(item.get("peer_url", "").rstrip("/") in keys or item.get("node_id") in keys for item in blocked.get("peers", []))


def block_peer(peer_url: str, node_id: str = "", reason: str = "manual") -> None:
    blocked = load_json_file(BLOCKED_PEERS_FILE, {"peers": []})
    peers = blocked.setdefault("peers", [])
    peer_url = peer_url.rstrip("/")
    record = {"peer_url": peer_url, "node_id": node_id, "reason": reason}
    for index, existing in enumerate(peers):
        if existing.get("peer_url", "").rstrip("/") == peer_url or (node_id and existing.get("node_id") == node_id):
            peers[index] = record
            break
    else:
        peers.append(record)
    save_json_file(BLOCKED_PEERS_FILE, blocked)
    audit_peer("peer_blocked", peer_url, {"node_id": node_id, "reason": reason})


def trust_peer(peer_url: str, node: dict) -> None:
    trusted = load_json_file(TRUSTED_PEERS_FILE, {"peers": []})
    peers = trusted.setdefault("peers", [])
    peer_url = peer_url.rstrip("/")
    node_id = node.get("node_id", "")
    record = {
        "peer_url": peer_url,
        "node_id": node_id,
        "public_key_id": node.get("public_key_id", ""),
        "public_key": node.get("public_key", {}),
        "trust_state": "tofu_trusted",
    }
    for index, existing in enumerate(peers):
        if existing.get("peer_url", "").rstrip("/") == peer_url or existing.get("node_id") == node_id:
            if existing.get("public_key_id") and existing.get("public_key_id") != record["public_key_id"]:
                audit_peer("peer_key_changed", peer_url, {"node_id": node_id, "old": existing.get("public_key_id"), "new": record["public_key_id"]})
                raise ValueError(f"trusted peer key changed: {peer_url}")
            peers[index] = record
            break
    else:
        peers.append(record)
    save_json_file(TRUSTED_PEERS_FILE, trusted)


def add_peer(peer_url: str, label: str = "", trust_state: str = "candidate") -> dict:
    peer_url = peer_url.rstrip("/")
    data = load_json_file(PEER_LIST_FILE, {"schema_version": "akashic.peer-list/v1", "peers": []})
    peers = data.setdefault("peers", [])
    record = {"peer_url": peer_url, "label": label, "trust_state": trust_state}
    for index, existing in enumerate(peers):
        if existing.get("peer_url", "").rstrip("/") == peer_url:
            peers[index] = {**existing, **record}
            break
    else:
        peers.append(record)
    save_json_file(PEER_LIST_FILE, data)
    return record


def normalize_peer_record(record, *, source: str = "") -> dict | None:
    if isinstance(record, str):
        peer_url = record.strip().rstrip("/")
        label = ""
        trust_state = "candidate"
    elif isinstance(record, dict):
        peer_url = str(record.get("peer_url") or record.get("url") or "").strip().rstrip("/")
        label = str(record.get("label") or "")
        trust_state = str(record.get("trust_state") or "candidate")
    else:
        return None
    if not peer_url.startswith(("http://", "https://")):
        return None
    normalized = {"peer_url": peer_url, "label": label, "trust_state": trust_state}
    if source:
        normalized["source"] = source
    return normalized


def import_peer_records(records: list, *, source: str = "", trust_state: str = "candidate") -> list[dict]:
    imported = []
    for raw in records:
        record = normalize_peer_record(raw, source=source)
        if not record:
            continue
        if is_blocked_peer(record["peer_url"]):
            audit_peer("peer_import_skipped_blocked", record["peer_url"], {"source": source})
            continue
        imported.append(add_peer(
            record["peer_url"],
            label=record.get("label") or source,
            trust_state=record.get("trust_state") or trust_state,
        ))
    return imported


def list_peers() -> list[dict]:
    data = load_json_file(PEER_LIST_FILE, {"schema_version": "akashic.peer-list/v1", "peers": []})
    return data.get("peers", [])


def peer_supports(hello: dict, family: str, version: str) -> bool:
    versions = hello.get("protocol_versions", {})
    supported = versions.get(family, [])
    return not supported or version in supported


def discover_peers(timeout: int = 5) -> dict:
    results = []
    for peer in list_peers():
        peer_url = peer.get("peer_url", "").rstrip("/")
        if not peer_url:
            continue
        try:
            session = handshake_peer(peer_url, timeout=timeout)
            manifest = session["manifest"]
            results.append({
                "peer_url": peer_url,
                "status": "ok",
                "node_id": manifest.get("node_id", ""),
                "genes": len(manifest.get("genes", [])),
                "signature_verified": bool(manifest.get("signature")),
            })
        except Exception as exc:
            audit_peer("peer_discovery_failed", peer_url, {"error": str(exc)})
            results.append({"peer_url": peer_url, "status": "failed", "error": str(exc)})
    return {"schema_version": "akashic.peer-discovery/v1", "peers": results}


def sync_peers(timeout: int = 5) -> dict:
    results = []
    imported_total = []
    for peer in list_peers():
        peer_url = peer.get("peer_url", "").rstrip("/")
        if not peer_url:
            continue
        try:
            session = handshake_peer(peer_url, timeout=timeout)
            manifest = session["manifest"]
            known = manifest.get("known_peers", [])
            imported = import_peer_records(known, source=f"gossip:{peer_url}")
            imported_total.extend(imported)
            results.append({
                "peer_url": peer_url,
                "status": "ok",
                "node_id": manifest.get("node_id", ""),
                "known_peers": len(known),
                "imported_peers": len(imported),
            })
            audit_peer("peer_sync_ok", peer_url, {"known_peers": len(known), "imported_peers": len(imported)})
        except Exception as exc:
            audit_peer("peer_sync_failed", peer_url, {"error": str(exc)})
            results.append({"peer_url": peer_url, "status": "failed", "error": str(exc)})
    return {
        "schema_version": "akashic.peer-sync/v1",
        "peers": results,
        "imported": imported_total,
    }


def load_bootstrap_source(source: str) -> dict:
    if source.startswith(("http://", "https://")):
        return fetch_json(source)
    path = Path(source)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def import_bootstrap(source: str) -> dict:
    payload = load_bootstrap_source(source)
    records = payload.get("peers", payload if isinstance(payload, list) else [])
    imported = import_peer_records(records, source=f"bootstrap:{source}")
    return {
        "schema_version": "akashic.bootstrap-import/v1",
        "source": source,
        "imported": imported,
        "count": len(imported),
    }


def beacon_scan(
    *,
    timeout: float = 2.0,
    udp_port: int = DEFAULT_BEACON_PORT,
    target_host: str = "255.255.255.255",
    register: bool = True,
) -> dict:
    found = []
    seen = set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        sock.sendto(BEACON_MESSAGE, (target_host, udp_port))
        while True:
            try:
                data, addr = sock.recvfrom(8192)
            except socket.timeout:
                break
            except OSError:
                break
            try:
                ack = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                if data == b"PROGENITOR_ACK":
                    ack = {"type": "PROGENITOR_ACK", "gateway_port": 8080, "genes": []}
                else:
                    continue
            if ack.get("type") != "PROGENITOR_ACK":
                continue
            gateway_port = int(ack.get("gateway_port") or 8080)
            peer_url = f"http://{addr[0]}:{gateway_port}"
            if peer_url in seen:
                continue
            seen.add(peer_url)
            record = {
                "peer_url": peer_url,
                "node_id": ack.get("node_id", ""),
                # a beacon's node_id is an UNVERIFIED claim — only the signed handshake binds id ⇄ key.
                # Pass this node_id to handshake_peer(expected_node_id=...) to catch a lying beacon.
                "id_verified": False,
                "hostname": ack.get("hostname", ""),
                "genes": len(ack.get("genes", [])),
                "source": "udp_beacon",
            }
            if register:
                add_peer(peer_url, label="udp-beacon")
            audit_peer("peer_beacon_discovered", peer_url, record)
            found.append(record)
    finally:
        sock.close()
    return {"schema_version": "akashic.beacon-scan/v1", "peers": found}


def fetch_json(url: str, timeout: int = 10) -> dict:
    with request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8-sig"))


def save_index(index: dict, path: Path = INDEX_FILE) -> None:
    payload = json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    except PermissionError:
        path.write_text(payload, encoding="utf-8")


def normalize_entry(name: str, entry, raw_base: str = DEFAULT_RAW_BASE) -> dict:
    if isinstance(entry, str):
        legacy_content_id = entry
        normalized = {}
    elif isinstance(entry, dict):
        legacy_content_id = entry.get("content_sha256") or entry.get("expected_sha256") or entry.get("cid") or entry.get("ipfs_cid")
        normalized = dict(entry)
    else:
        raise ValueError(f"index entry for {name!r} must be a string or object")

    content_sha = normalized.get("content_sha256") or normalized.get("expected_sha256") or legacy_content_id
    registry_path = normalized.get("registry_path") or (f"genes/{content_sha}" if content_sha else "")

    transport_hints = list(normalized.get("transport_hints") or [])
    def add_hint(kind: str, url: str, priority: int) -> None:
        if url and not any(h.get("type") == kind and h.get("url") == url for h in transport_hints):
            transport_hints.append({"type": kind, "url": url, "priority": priority})

    if registry_path:
        add_hint("registry_path", registry_path, 10)
        add_hint("github_raw", f"{raw_base.rstrip('/')}/{registry_path}", 70)
    if normalized.get("ipfs_cid"):
        add_hint("ipfs", normalized["ipfs_cid"], 40)
    if normalized.get("peer_hint"):
        add_hint("peer", normalized["peer_hint"], 30)

    normalized.update(
        {
            "schema_version": normalized.get("schema_version", SCHEMA_VERSION),
            "capability": normalized.get("capability", name),
            "content_id": content_sha,
            "cid": content_sha,
            "content_sha256": content_sha,
            "expected_sha256": content_sha,
            "registry_path": registry_path,
            "transport_hints": sorted(transport_hints, key=lambda h: h.get("priority", 100)),
            "trust_state": normalized.get("trust_state", "registry_verified"),
        }
    )
    return normalized


def normalize_index(index: dict) -> dict:
    return {name: normalize_entry(name, entry) for name, entry in sorted(index.items())}


def verify_index(index: dict) -> list[dict]:
    issues = []
    for name, raw_entry in index.items():
        try:
            entry = normalize_entry(name, raw_entry)
        except ValueError as exc:
            issues.append({"name": name, "level": "error", "reason": str(exc)})
            continue

        content_sha = entry.get("content_sha256", "")
        if len(content_sha) != 64:
            issues.append({"name": name, "level": "error", "reason": "content_sha256 must be 64 hex characters"})
            continue

        registry_path = entry.get("registry_path", "")
        local_path = REGISTRY_DIR / registry_path
        if not local_path.exists():
            issues.append({"name": name, "level": "error", "reason": f"registry_path missing: {registry_path}"})
            continue

        actual = sha256_file(local_path)
        if actual != content_sha:
            issues.append({"name": name, "level": "error", "reason": f"sha mismatch: expected {content_sha}, actual {actual}"})
    return issues


def load_registry_public_key() -> dict | None:
    """[P0] Load the registry public key from env or fall back to the default."""
    env_val = os.environ.get("PROGENITOR_REGISTRY_PUBLIC_KEY", "")
    if env_val:
        try:
            return json.loads(env_val)
        except json.JSONDecodeError:
            pass
    # Default public key — hard-coded for the official progenitor-registry
    return {
        "key_type": "progenitor-rsa-pkcs1-sha256-v1",
        "n": "ZRM8Gjp922d9mth97wQcqyVhvCzSQCSt5DduHe_KH8zB2dAldhIdIkqPfRIoFN9IxUxYkrUod4FoVjWqgqRUZoaOXbndCZeOY4OfqXgKEY52t4PeV0W2Kq_lL94Zt0M-tTuJmF17Dkpvn4RH9Wze17cUq9L8IV4H7tuGJyiu4u0s2N5HVjhDrGDtKWEZQ_0nZ_OK98pVEk25ELwnUqzabvaGAZdEvEdrKfNoeyM3jIxYqkgf04wfBXQDms6EJ5tazq8GyKNOZMNrq4AnGQXkas1Z2bAb0EdgLczUKUcJ3ogtT0ZYfYzaTSbGZ2TgsIT5Y4RyNEnJyBza2YERexJlYQ",
        "e": 65537,
    }


def verify_index_signature(index_path: Path | None = None) -> list[dict]:
    """[P0] Verify the cryptographic signature on .akashic_index.json.

    Returns a list of issues (empty = signature valid).
    An ``index_path`` pointing to the index is required; the ``.sig`` file must
    sit next to it. If no path is given, the default ``INDEX_FILE`` is used.
    """
    index_path = index_path or INDEX_FILE
    sig_path = index_path.with_suffix(index_path.suffix + ".sig")
    issues = []

    if not sig_path.exists():
        issues.append({"name": "index-signature", "level": "error",
                       "reason": f"signature file missing: {sig_path}"})
        return issues

    if not index_path.exists():
        issues.append({"name": "index-signature", "level": "error",
                       "reason": f"index file missing: {index_path}"})
        return issues

    try:
        envelope = json.loads(sig_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        issues.append({"name": "index-signature", "level": "error",
                       "reason": f"sig read error: {exc}"})
        return issues

    if envelope.get("schema_version") != "akashic.index-signature/v1":
        issues.append({"name": "index-signature", "level": "error",
                       "reason": "unknown schema_version"})
        return issues

    public_key = load_registry_public_key()
    if not public_key:
        issues.append({"name": "index-signature", "level": "error",
                       "reason": "no registry public key configured"})
        return issues

    from stargate_identity import verify_document
    if not verify_document(envelope, public_key):
        issues.append({"name": "index-signature", "level": "error",
                       "reason": "cryptographic signature invalid"})
        return issues

    # Verify the signed hash matches the actual index
    signed_hash = envelope.get("index_sha256", "")
    actual_hash = hashlib.sha256(index_path.read_bytes()).hexdigest()
    if signed_hash != actual_hash:
        issues.append({"name": "index-signature", "level": "error",
                       "reason": f"index_sha256 mismatch: signed={signed_hash[:16]}... actual={actual_hash[:16]}..."})

    return issues


def fetch_local_registry(entry: dict) -> tuple[str, bytes] | None:
    registry_path = entry.get("registry_path")
    if not registry_path:
        return None
    path = REGISTRY_DIR / registry_path
    if not path.exists():
        return None
    return str(path), path.read_bytes()


def fetch_peer(entry: dict, timeout: int = 10) -> tuple[str, bytes] | None:
    for hint in entry.get("transport_hints", []):
        if hint.get("type") != "peer":
            continue
        url = hint.get("url", "").rstrip("/")
        if not url:
            continue
        try:
            with request.urlopen(f"{url}/gene/{entry['capability']}", timeout=timeout) as resp:
                return url, resp.read()
        except Exception:
            continue
    return None


def fetch_peer_gene_by_hash(peer_url: str, content_sha256: str, timeout: int = 10) -> tuple[str, bytes] | None:
    url = f"{peer_url.rstrip('/')}/gene/{content_sha256}"
    with request.urlopen(url, timeout=timeout) as resp:
        return url, resp.read()


def fetch_github_raw(entry: dict, timeout: int = 15) -> tuple[str, bytes] | None:
    for hint in entry.get("transport_hints", []):
        if hint.get("type") != "github_raw":
            continue
        url = hint.get("url")
        if not url:
            continue
        try:
            with request.urlopen(url, timeout=timeout) as resp:
                return url, resp.read()
        except Exception:
            continue
    return None


def resolve_gene(name: str, *, allow_network: bool = False, peer_manifest: Path | None = None) -> ResolvedGene:
    index = normalize_index(load_index())
    if peer_manifest and peer_manifest.exists():
        peer_data = json.loads(peer_manifest.read_text(encoding="utf-8-sig"))
        for item in peer_data.get("genes", []):
            cap = item.get("capability") or item.get("name")
            if cap and cap not in index:
                index[cap] = normalize_entry(cap, item)

    if name not in index:
        raise KeyError(f"unknown capability: {name}")

    entry = index[name]
    attempts = [fetch_local_registry(entry)]
    if allow_network:
        attempts.extend([fetch_peer(entry), fetch_github_raw(entry)])

    for result in attempts:
        if not result:
            continue
        source, payload = result
        actual = sha256_bytes(payload)
        expected = entry.get("content_sha256")
        if actual != expected:
            raise ValueError(f"resolved payload hash mismatch from {source}: expected {expected}, actual {actual}")
        return ResolvedGene(name=name, content_sha256=expected, source=source, payload=payload, entry=entry)

    raise FileNotFoundError(f"no usable transport found for {name}")


def build_peer_manifest(index: dict, node_id: str = "local", identity: dict | None = None) -> dict:
    normalized = normalize_index(index)
    manifest = {
        "schema_version": "akashic.peer-manifest/v1",
        "protocol_versions": {
            "peer_manifest": [PEER_MANIFEST_VERSION],
            "gene_transfer": [GENE_TRANSFER_VERSION],
            "peer_exchange": [PEER_EXCHANGE_VERSION],
        },
        "node_id": node_id,
        "genes": [
            {
                "capability": name,
                "content_sha256": entry.get("content_sha256"),
                "registry_path": entry.get("registry_path"),
                "trust_state": entry.get("trust_state"),
                "transport_hints": entry.get("transport_hints", []),
            }
            for name, entry in normalized.items()
        ],
        "known_peers": [],
    }
    if identity:
        manifest["node"] = {
            "schema_version": identity.get("schema_version", "akashic.node-identity/v1"),
            "node_id": identity["node_id"],
            "label": identity.get("label", ""),
            "key_type": identity["key_type"],
            "public_key": identity["public_key"],
            "public_key_id": identity["public_key_id"],
        }
        manifest["node_id"] = identity["node_id"]
        manifest = sign_document(manifest, identity)
    return manifest


def handshake_peer(peer_url: str, *, trust_on_first_use: bool = True, timeout: int = 10,
                   expected_node_id: str = "") -> dict:
    peer_url = peer_url.rstrip("/")
    hello = fetch_json(f"{peer_url}/hello", timeout=timeout)
    node = hello.get("node") or {}
    node_id = node.get("node_id", "")
    if hello.get("schema_version") != HELLO_VERSION:
        audit_peer("peer_hello_version_unknown", peer_url, {"schema_version": hello.get("schema_version")})
    if not peer_supports(hello, "peer_manifest", PEER_MANIFEST_VERSION):
        audit_peer("peer_protocol_unsupported", peer_url, {"family": "peer_manifest", "required": PEER_MANIFEST_VERSION})
        raise ValueError(f"peer does not support {PEER_MANIFEST_VERSION}")
    if is_blocked_peer(peer_url, node_id):
        audit_peer("blocked_peer_rejected", peer_url, {"node_id": node_id})
        raise PermissionError(f"blocked peer: {peer_url}")

    # Self-certifying identity: node_id must equal the key fingerprint (== public_key_id), so the
    # id is an unforgeable claim rather than an arbitrary string. The manifest signature below then
    # proves the peer actually holds that key. Together they bind name → key with no central authority.
    if not verify_node_identity(node):
        audit_peer("peer_identity_not_self_certifying", peer_url,
                   {"node_id": node_id, "public_key_id": node.get("public_key_id", "")})
        raise ValueError("peer node identity is not self-certifying (node_id must equal key fingerprint)")

    # Bind a discovery-layer claim to the verified key: if we reached this peer via a beacon that
    # advertised a node_id, the cryptographically-verified node_id must match it — else the beacon lied.
    if expected_node_id and node_id != expected_node_id:
        audit_peer("peer_beacon_id_mismatch", peer_url, {"claimed": expected_node_id, "verified": node_id})
        raise ValueError("beacon-advertised node_id does not match the verified key fingerprint")

    manifest = fetch_json(f"{peer_url}/manifest", timeout=timeout)
    if manifest.get("schema_version") != PEER_MANIFEST_VERSION:
        audit_peer("peer_manifest_version_unknown", peer_url, {"schema_version": manifest.get("schema_version")})
    if manifest.get("node", {}).get("public_key_id") != node.get("public_key_id"):
        audit_peer("peer_identity_mismatch", peer_url, {"hello_node": node, "manifest_node": manifest.get("node")})
        raise ValueError("peer identity mismatch between /hello and /manifest")
    if not verify_document(manifest, node.get("public_key")):
        audit_peer("peer_manifest_signature_failed", peer_url, {"node_id": node_id})
        raise ValueError("peer manifest signature verification failed")

    if trust_on_first_use:
        trust_peer(peer_url, node)
    audit_peer("peer_handshake_ok", peer_url, {"node_id": node_id, "genes": len(manifest.get("genes", []))})
    return {"peer_url": peer_url, "hello": hello, "manifest": manifest}


def resolve_from_peer(peer_url: str, name: str, *, trust_on_first_use: bool = True, timeout: int = 10) -> ResolvedGene:
    session = handshake_peer(peer_url, trust_on_first_use=trust_on_first_use, timeout=timeout)
    manifest = session["manifest"]
    entry = None
    for item in manifest.get("genes", []):
        if item.get("capability") == name or item.get("content_sha256") == name:
            entry = normalize_entry(item.get("capability") or name, item)
            break
    if not entry:
        audit_peer("peer_gene_missing", peer_url, {"name": name})
        raise KeyError(f"peer does not advertise capability: {name}")

    source, payload = fetch_peer_gene_by_hash(peer_url, entry["content_sha256"], timeout=timeout)
    actual = sha256_bytes(payload)
    if actual != entry["content_sha256"]:
        audit_peer("peer_payload_hash_mismatch", peer_url, {"expected": entry["content_sha256"], "actual": actual})
        raise ValueError(f"peer payload hash mismatch: expected {entry['content_sha256']}, actual {actual}")
    audit_peer("peer_resolve_ok", peer_url, {"name": entry["capability"], "content_sha256": actual, "bytes": len(payload)})
    return ResolvedGene(name=entry["capability"], content_sha256=actual, source=source, payload=payload, entry=entry)


def write_health_report(index: dict, issues: list[dict]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / "stargate_health_report.json"
    peers = list_peers()
    trusted = load_json_file(TRUSTED_PEERS_FILE, {"peers": []}).get("peers", [])
    blocked = load_json_file(BLOCKED_PEERS_FILE, {"peers": []}).get("peers", [])
    payload = {
        "schema_version": "akashic.health/v1",
        "capabilities": len(index),
        "issues": issues,
        "peer_mesh": {
            "configured_peers": len(peers),
            "trusted_peers": len(trusted),
            "blocked_peers": len(blocked),
            "udp_beacon_supported": True,
            "signed_handshake_supported": True,
            "peer_exchange_supported": True,
            "bootstrap_import_supported": True,
        },
        "status": "ok" if not issues else "degraded",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve and verify Akashic Stargate capabilities.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("normalize-index")
    sub.add_parser("verify-index")
    p_resolve = sub.add_parser("resolve")
    p_resolve.add_argument("name")
    p_resolve.add_argument("--network", action="store_true")
    p_peer = sub.add_parser("peer-handshake")
    p_peer.add_argument("peer_url")
    p_peer_resolve = sub.add_parser("peer-resolve")
    p_peer_resolve.add_argument("peer_url")
    p_peer_resolve.add_argument("name")
    p_peer_add = sub.add_parser("peer-add")
    p_peer_add.add_argument("peer_url")
    p_peer_add.add_argument("--label", default="")
    sub.add_parser("peer-list")
    p_peer_block = sub.add_parser("peer-block")
    p_peer_block.add_argument("peer_url")
    p_peer_block.add_argument("--node-id", default="")
    p_peer_block.add_argument("--reason", default="manual")
    sub.add_parser("peer-discover")
    sub.add_parser("peer-sync")
    p_bootstrap = sub.add_parser("peer-bootstrap")
    p_bootstrap.add_argument("source")
    p_beacon = sub.add_parser("peer-beacon-scan")
    p_beacon.add_argument("--timeout", type=float, default=2.0)
    p_beacon.add_argument("--udp-port", type=int, default=DEFAULT_BEACON_PORT)
    p_beacon.add_argument("--target-host", default="255.255.255.255")
    p_beacon.add_argument("--no-register", action="store_true")
    p_manifest = sub.add_parser("peer-manifest")
    p_manifest.add_argument("--node-id", default="local")
    sub.add_parser("health")
    args = parser.parse_args()

    if args.command == "normalize-index":
        index = normalize_index(load_index())
        save_index(index)
        print(f"normalized {len(index)} entries in {INDEX_FILE}")
        return 0

    if args.command == "verify-index":
        index = normalize_index(load_index())
        issues = verify_index(index)
        sig_issues = verify_index_signature()
        issues.extend(sig_issues)
        print(f"verified {len(index)} entries; issues={len(issues)}")
        for issue in issues[:20]:
            print(f"{issue['level']}: {issue['name']}: {issue['reason']}")
        return 0 if not issues else 1

    if args.command == "resolve":
        resolved = resolve_gene(args.name, allow_network=args.network)
        print(json.dumps({"name": resolved.name, "source": resolved.source, "content_sha256": resolved.content_sha256, "bytes": len(resolved.payload)}, indent=2))
        return 0

    if args.command == "peer-handshake":
        session = handshake_peer(args.peer_url)
        manifest = session["manifest"]
        print(json.dumps({
            "peer_url": session["peer_url"],
            "node_id": manifest.get("node_id"),
            "public_key_id": manifest.get("node", {}).get("public_key_id"),
            "genes": len(manifest.get("genes", [])),
            "signature_verified": True,
        }, ensure_ascii=False, indent=2))
        return 0

    if args.command == "peer-resolve":
        resolved = resolve_from_peer(args.peer_url, args.name)
        print(json.dumps({
            "name": resolved.name,
            "source": resolved.source,
            "content_sha256": resolved.content_sha256,
            "bytes": len(resolved.payload),
        }, ensure_ascii=False, indent=2))
        return 0

    if args.command == "peer-add":
        record = add_peer(args.peer_url, label=args.label)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0

    if args.command == "peer-list":
        print(json.dumps({"schema_version": "akashic.peer-list/v1", "peers": list_peers()}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "peer-block":
        block_peer(args.peer_url, node_id=args.node_id, reason=args.reason)
        print(json.dumps({"blocked": args.peer_url.rstrip("/"), "node_id": args.node_id, "reason": args.reason}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "peer-discover":
        print(json.dumps(discover_peers(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "peer-sync":
        print(json.dumps(sync_peers(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "peer-bootstrap":
        print(json.dumps(import_bootstrap(args.source), ensure_ascii=False, indent=2))
        return 0

    if args.command == "peer-beacon-scan":
        print(json.dumps(
            beacon_scan(
                timeout=args.timeout,
                udp_port=args.udp_port,
                target_host=args.target_host,
                register=not args.no_register,
            ),
            ensure_ascii=False,
            indent=2,
        ))
        return 0

    if args.command == "peer-manifest":
        manifest = build_peer_manifest(load_index(), node_id=args.node_id)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if args.command == "health":
        index = normalize_index(load_index())
        issues = verify_index(index)
        sig_issues = verify_index_signature()
        issues.extend(sig_issues)
        path = write_health_report(index, issues)
        print(f"wrote {path}")
        print(f"status={'ok' if not issues else 'degraded'} capabilities={len(index)} issues={len(issues)}")
        return 0 if not issues else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
