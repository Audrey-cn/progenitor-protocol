"""R4 Stage 1 — seccomp-BPF hardening inside the gene cage (Linux x86-64).

Runs _sandbox_worker the way production does — in a child process — so the kernel
filter never leaks into the pytest process. Linux-only assertions are skipped elsewhere
(the hardening itself degrades honestly on non-Linux hosts).
"""
import json
import multiprocessing
import os
import platform
import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "hatchery"))

LINUX_X64 = sys.platform == "linux" and platform.machine().lower() in ("x86_64", "amd64")
CTX = multiprocessing.get_context("spawn" if sys.platform == "win32" else "fork")


def _run_worker(tmp_path, monkeypatch, gene_code):
    """Execute a gene through the real _sandbox_worker in a child process; return the result."""
    monkeypatch.setenv("PROGENITOR_ALLOW_GENE_EXEC", "1")
    engine = pytest.importorskip("engine") if False else __import__("engine")
    gene = tmp_path / "g.py"
    gene.write_text(gene_code, encoding="utf-8", newline="")
    q = CTX.Queue()
    p = CTX.Process(target=engine._sandbox_worker,
                    args=(q, str(gene), "main", {}, 50, 10))
    p.start()
    p.join(60)
    assert p.exitcode == 0, f"cage crashed: exitcode={p.exitcode}"
    item = q.get(timeout=10)
    return item


def test_benign_gene_runs_with_hardening_armed(tmp_path, monkeypatch):
    """A benign compute gene works whether or not the hardening applied (all platforms)."""
    item = _run_worker(tmp_path, monkeypatch, "def main():\n    return len([1, 2, 3])\n")
    assert item["status"] == "success"
    assert item["result"] == 3
    assert isinstance(item.get("hardening"), dict)  # reported either way


@pytest.mark.skipif(not LINUX_X64, reason="seccomp path is Linux x86-64 only")
def test_seccomp_blocks_socket(tmp_path, monkeypatch):
    item = _run_worker(
        tmp_path, monkeypatch,
        "def main():\n"
        "    import socket\n"
        "    s = socket.socket()\n"
        "    return 'socket opened'\n")
    assert item["status"] == "error", item
    assert "PermissionError" in item["error"], item
    assert item["hardening"]["applied"] is True


@pytest.mark.skipif(not LINUX_X64, reason="seccomp path is Linux x86-64 only")
def test_seccomp_blocks_write_open(tmp_path, monkeypatch):
    item = _run_worker(
        tmp_path, monkeypatch,
        "def main():\n"
        "    f = open('/tmp/progenitor_escape_probe', 'w')\n"
        "    f.write('x')\n"
        "    return 'wrote'\n")
    assert item["status"] == "error", item
    assert "PermissionError" in item["error"], item


@pytest.mark.skipif(not LINUX_X64, reason="differential proof only matters where seccomp arms")
def test_escape_hatch_disables_filter(tmp_path, monkeypatch):
    """PROGENITOR_SANDBOX_SECCOMP=off → socket() succeeds (proves the filter was the blocker)."""
    monkeypatch.setenv("PROGENITOR_SANDBOX_SECCOMP", "off")
    item = _run_worker(
        tmp_path, monkeypatch,
        "def main():\n"
        "    import socket\n"
        "    s = socket.socket()\n"
        "    s.close()\n"
        "    return 'opened'\n")
    assert item["status"] == "success", item
    assert item["hardening"]["applied"] is False


@pytest.mark.skipif(not LINUX_X64, reason="read-only imports survive the filter (linux check)")
def test_imports_still_work_under_filter(tmp_path, monkeypatch):
    item = _run_worker(
        tmp_path, monkeypatch,
        "def main():\n"
        "    import json, re\n"
        "    return json.dumps({'ok': bool(re.match(r'a', 'abc'))})\n")
    assert item["status"] == "success", item
    assert json.loads(item["result"]) == {"ok": True}
