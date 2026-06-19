import hashlib
import json
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
REGISTRY_DIR = REPO_DIR.parent / "progenitor-registry"
HATCHERY_DIR = REPO_DIR / "hatchery"
TOOLS_DIR = REPO_DIR / "tools"

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(HATCHERY_DIR))

import stargate_resolver


def test_registry_entries_use_content_sha256_as_primary_identity():
    index = stargate_resolver.normalize_index(stargate_resolver.load_index())
    assert index

    for name, entry in index.items():
        assert entry["capability"] == name
        assert len(entry["content_sha256"]) == 64
        assert entry["expected_sha256"] == entry["content_sha256"]
        assert entry["registry_path"] == f"genes/{entry['content_sha256']}"
        assert entry["content_id"] == entry["content_sha256"]
        assert entry["cid"] == entry["content_sha256"]


def test_transport_hints_represent_registry_and_github_mirrors():
    index = stargate_resolver.normalize_index(stargate_resolver.load_index())
    for entry in index.values():
        hints = entry["transport_hints"]
        assert hints[0]["type"] == "registry_path"
        assert hints[0]["url"] == entry["registry_path"]
        assert any(h["type"] == "github_raw" for h in hints)


def test_ipfs_is_optional_transport_hint_not_primary_identity():
    entry = stargate_resolver.normalize_entry(
        "ipfs-optional",
        {
            "content_sha256": "e" * 64,
            "ipfs_cid": "bafyoptionaltransportcid",
        },
    )

    assert entry["content_sha256"] == "e" * 64
    assert entry["cid"] == "e" * 64
    assert any(h["type"] == "ipfs" and h["url"] == "bafyoptionaltransportcid" for h in entry["transport_hints"])


def test_local_registry_payloads_match_content_sha256():
    index = stargate_resolver.normalize_index(stargate_resolver.load_index())
    for entry in index.values():
        payload_path = REGISTRY_DIR / entry["registry_path"]
        payload = payload_path.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["content_sha256"]


def test_legacy_string_entry_is_normalized_without_network():
    normalized = stargate_resolver.normalize_entry("legacy-string", "f" * 64)
    assert normalized["content_sha256"] == "f" * 64
    assert normalized["registry_path"] == "genes/" + "f" * 64
    assert any(h["type"] == "registry_path" for h in normalized["transport_hints"])
    assert any(h["type"] == "github_raw" for h in normalized["transport_hints"])
