"""[transport] Transport-hint ladder — resilient, content-verified, multi-path gene acquisition.

Federation layer (docs/VISION.md). A gene advertises several ``transport_hints`` — e.g.
``registry_path`` (local), ``github_raw`` / ``peer`` (HTTP), ``ipfs`` (gateway array) — each with a
priority. ``resolve_transport`` walks them in priority order via a pluggable fetcher and returns
the first payload whose SHA-256 matches the expected content hash. Content-addressing makes every
path equally trustworthy — a stranger's mirror is fine because the bytes are verified — which is
what lets propagation go LAN → WAN without a central server.

Pure and offline-testable by design: the fetcher is injected, so the ladder logic is exercised
with no real network; the real fetchers (file / HTTP / IPFS) are stdlib-only and plug in at the
edges (and degrade gracefully when a transport — e.g. IPFS with no daemon — is unavailable).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from urllib import request

HTTP_TYPES = ("github_raw", "peer", "http", "https")
DEFAULT_MAX_BYTES = 8 * 1024 * 1024


def _priority(hint):
    return hint.get("priority", 100)


def resolve_transport(transport_hints, expected_sha256, fetcher, *, allow_types=None):
    """Walk hints by priority and return the first content-verified payload.

    fetcher(hint) -> bytes | None | raises. A hint whose bytes don't match ``expected_sha256`` is a
    miss and the ladder continues. ``allow_types`` optionally restricts which transport types are
    tried (e.g. drop ``ipfs``/``github_raw`` when offline). Returns:
        {"status": "fetched"|"exhausted", "bytes": ..., "transport": type, "url": ..., "attempts": [...]}
    """
    attempts = []
    for hint in sorted(transport_hints or [], key=_priority):
        ttype = hint.get("type", "unknown")
        url = hint.get("url")
        if allow_types is not None and ttype not in allow_types:
            attempts.append({"type": ttype, "url": url, "result": "skipped"})
            continue
        try:
            payload = fetcher(hint)
        except Exception as exc:
            attempts.append({"type": ttype, "url": url, "result": f"error: {type(exc).__name__}"})
            continue
        if payload is None:
            attempts.append({"type": ttype, "url": url, "result": "unavailable"})
            continue
        if expected_sha256 and hashlib.sha256(payload).hexdigest() != expected_sha256:
            attempts.append({"type": ttype, "url": url, "result": "hash_mismatch"})
            continue
        attempts.append({"type": ttype, "url": url, "result": "ok"})
        return {"status": "fetched", "bytes": payload, "transport": ttype, "url": url, "attempts": attempts}
    return {"status": "exhausted", "bytes": None, "transport": None, "url": None, "attempts": attempts}


# --- real, stdlib-only fetchers (plug into resolve_transport at the edges) ------------------

def make_file_fetcher(base_dir):
    base = Path(base_dir)

    def _fetch(hint):
        target = base / hint.get("url", "")
        return target.read_bytes() if target.is_file() else None
    return _fetch


def make_http_fetcher(timeout=15, max_bytes=DEFAULT_MAX_BYTES):
    def _fetch(hint):
        url = hint.get("url")
        if not url:
            return None
        req = request.Request(url, headers={"User-Agent": "progenitor-transport/1.0"})
        with request.urlopen(req, timeout=timeout) as response:
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise RuntimeError(f"payload exceeds {max_bytes} bytes — refusing")
            return data
    return _fetch


def make_ipfs_fetcher(gateways, timeout=15, max_bytes=DEFAULT_MAX_BYTES):
    def _fetch(hint):
        cid = hint.get("url") or hint.get("cid")
        if not cid:
            return None
        for gateway in gateways or []:
            try:
                req = request.Request(f"{gateway.rstrip('/')}/{cid.strip()}",
                                      headers={"User-Agent": "progenitor-transport/1.0"})
                with request.urlopen(req, timeout=timeout) as response:
                    data = response.read(max_bytes + 1)
                    if len(data) > max_bytes:
                        raise RuntimeError("payload exceeds cap")
                    return data
            except Exception:
                continue
        return None
    return _fetch


def default_fetcher(*, base_dir=None, gateways=None, timeout=15, max_bytes=DEFAULT_MAX_BYTES):
    """A dispatching fetcher that routes each hint to the right transport by ``type``."""
    file_f = make_file_fetcher(base_dir) if base_dir else (lambda hint: None)
    http_f = make_http_fetcher(timeout, max_bytes)
    ipfs_f = make_ipfs_fetcher(gateways, timeout, max_bytes) if gateways else (lambda hint: None)

    def _fetch(hint):
        ttype = hint.get("type")
        if ttype == "registry_path":
            return file_f(hint)
        if ttype in HTTP_TYPES:
            return http_f(hint)
        if ttype == "ipfs":
            return ipfs_f(hint)
        url = hint.get("url", "")
        return http_f(hint) if url.startswith("http") else None
    return _fetch
