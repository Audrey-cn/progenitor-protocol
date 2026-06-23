"""Transport-hint ladder — priority order, content-verified fallback, real loopback HTTP (federation)."""
import functools
import hashlib
import http.server
import socketserver
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hatchery"))
import transport  # noqa: E402
import engine  # noqa: E402

GENE = b"# purity: pure\ndef main(x):\n    return x + 1\n"
SHA = hashlib.sha256(GENE).hexdigest()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silence per-request logging
        pass


def _serve(directory):
    handler = functools.partial(_QuietHandler, directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


# --- ladder logic (injected fetchers, no network) ------------------------------------------

def test_picks_highest_priority_that_succeeds():
    hints = [
        {"type": "ipfs", "url": "cid", "priority": 70},
        {"type": "registry_path", "url": "genes/x", "priority": 10},
    ]
    fetcher = lambda h: GENE if h["type"] == "registry_path" else None  # noqa: E731
    out = transport.resolve_transport(hints, SHA, fetcher)
    assert out["status"] == "fetched" and out["transport"] == "registry_path"


def test_falls_back_past_unavailable_and_errors():
    hints = [
        {"type": "peer", "url": "a", "priority": 1},
        {"type": "github_raw", "url": "b", "priority": 5},
        {"type": "registry_path", "url": "c", "priority": 10},
    ]
    def fetcher(h):
        if h["type"] == "peer":
            raise ConnectionError("refused")
        if h["type"] == "github_raw":
            return None  # unavailable
        return GENE
    out = transport.resolve_transport(hints, SHA, fetcher)
    assert out["transport"] == "registry_path"
    results = [a["result"] for a in out["attempts"]]
    assert results[0].startswith("error") and results[1] == "unavailable" and results[2] == "ok"


def test_rejects_hash_mismatch_and_continues():
    hints = [
        {"type": "peer", "url": "evil", "priority": 1},
        {"type": "registry_path", "url": "good", "priority": 10},
    ]
    fetcher = lambda h: b"tampered" if h["type"] == "peer" else GENE  # noqa: E731
    out = transport.resolve_transport(hints, SHA, fetcher)
    assert out["transport"] == "registry_path"
    assert out["attempts"][0]["result"] == "hash_mismatch"


def test_allow_types_skips_wan_when_offline():
    hints = [
        {"type": "github_raw", "url": "wan", "priority": 5},
        {"type": "registry_path", "url": "local", "priority": 10},
    ]
    fetcher = lambda h: GENE  # noqa: E731 (every transport "would" work)
    out = transport.resolve_transport(hints, SHA, fetcher, allow_types={"registry_path", "peer"})
    assert out["transport"] == "registry_path"
    assert out["attempts"][0]["result"] == "skipped"


def test_exhausted_when_all_fail():
    hints = [{"type": "peer", "url": "x", "priority": 1}]
    out = transport.resolve_transport(hints, SHA, lambda h: None)
    assert out["status"] == "exhausted" and out["bytes"] is None


# --- real network paths over loopback ------------------------------------------------------

def test_file_fetcher_reads_local(tmp_path):
    (tmp_path / SHA).write_bytes(GENE)
    fetcher = transport.make_file_fetcher(tmp_path)
    assert fetcher({"type": "registry_path", "url": SHA}) == GENE


def test_loopback_http_fetch_and_verify(tmp_path):
    (tmp_path / SHA).write_bytes(GENE)
    httpd, port = _serve(tmp_path)
    try:
        hints = [{"type": "github_raw", "url": f"http://127.0.0.1:{port}/{SHA}", "priority": 10}]
        out = transport.resolve_transport(hints, SHA, transport.default_fetcher())
        assert out["status"] == "fetched" and out["bytes"] == GENE and out["transport"] == "github_raw"
    finally:
        httpd.shutdown()


def test_ladder_dead_peer_then_loopback_http(tmp_path):
    (tmp_path / SHA).write_bytes(GENE)
    httpd, port = _serve(tmp_path)
    try:
        hints = [
            {"type": "peer", "url": "http://127.0.0.1:1/x", "priority": 5},  # refused
            {"type": "github_raw", "url": f"http://127.0.0.1:{port}/{SHA}", "priority": 10},
        ]
        out = transport.resolve_transport(hints, SHA, transport.default_fetcher())
        assert out["status"] == "fetched" and out["transport"] == "github_raw"
        assert out["attempts"][0]["result"].startswith("error")
    finally:
        httpd.shutdown()


# --- engine wiring: acquire_gene → (feeds adoption) ----------------------------------------

def test_phagocyte_acquire_gene_over_loopback(tmp_path):
    (tmp_path / SHA).write_bytes(GENE)
    httpd, port = _serve(tmp_path)
    try:
        entry = {
            "capability": "demo",
            "content_sha256": SHA,
            "transport_hints": [{"type": "github_raw", "url": f"http://127.0.0.1:{port}/{SHA}", "priority": 10}],
        }
        phg = engine.Phagocyte()
        out = phg.acquire_gene(entry)
        assert out["status"] == "fetched" and out["bytes"] == GENE
        # the acquired bytes flow into the voluntary-adoption decision (never auto-run)
        proposed = phg.propose_adoption(out["bytes"], index_entry=entry)
        assert proposed["proposal"]["hash_verified"] is True
    finally:
        httpd.shutdown()


def test_acquire_gene_offline_skips_wan(tmp_path):
    entry = {
        "content_sha256": SHA,
        "transport_hints": [{"type": "github_raw", "url": "http://example.invalid/x", "priority": 10}],
    }
    out = engine.Phagocyte().acquire_gene(entry, offline=True)
    assert out["status"] == "exhausted"
    assert out["attempts"][0]["result"] == "skipped"
