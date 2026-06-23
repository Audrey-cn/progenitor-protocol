"""[compass] Registry index helpers — extracted from engine.py (P2 modularization).

The incubator inlines this module into the .pgn payload at build time so the shipped
seed stays a single self-contained file.
"""
import json
import os
from typing import Optional


def compass_load_index(index_path: str) -> dict:
    """Load the Akashic index file."""
    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def compass_resolve_cid_by_name(name: str, index_data: dict) -> Optional[str]:
    """Resolve a semantic capability name to its CID."""
    entries = index_data.get("entries", {})
    if name in entries:
        return entries[name].get("cid")
    for key, value in entries.items():
        if name.lower() in key.lower() or key.lower() in name.lower():
            return value.get("cid")
    return None


def compass_update_index(index_path: str, updates: dict):
    """Update the index file with new entries."""
    existing = compass_load_index(index_path)
    existing.update(updates)
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def _read_capped(response, limit):
    """[F004] Read at most ``limit`` bytes; raise if the body exceeds it (DoS guard)."""
    data = response.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError(f"response exceeds {limit} bytes — refusing (possible DoS)")
    return data
