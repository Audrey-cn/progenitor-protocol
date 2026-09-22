"""R4 Stage 1 - seccomp-BPF hardening probe tests (Linux x86-64, verified on ubuntu CI).

A child process installs the filter via sandbox_linux.apply_sandbox_hardening() and then
probes syscalls one by one (read / write / socket). The probe output is embedded in the
assertions, so a CI failure shows exactly which syscall behaved unexpectedly.

The _sandbox_worker wiring keeps a light smoke test: the restricted builtins of the gene
sandbox are compute-only (no import/open), so kernel syscalls cannot be exercised from
inside a gene - that is exactly why the kernel filter exists (defense against escapes).
"""
import json
import multiprocessing
import platform
import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "hatchery"))
HATCHERY = REPO_DIR / "hatchery"
LINUX_X64 = sys.platform == "linux" and platform.machine().lower() in ("x86_64", "amd64")
CTX = multiprocessing.get_context("spawn" if sys.platform == "win32" else "fork")

PROBE_SRC = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from sandbox_linux import apply_sandbox_hardening\n"
    "out = {'hardening': apply_sandbox_hardening()}\n"
    "try:\n"
    "    with open(sys.argv[2], 'rb') as f:\n"
    "        f.read(8)\n"
    "    out['read'] = 'ok'\n"
    "except Exception as e:\n"
    "    out['read'] = type(e).__name__\n"
    "try:\n"
    "    f = open(sys.argv[3], 'wb')\n"
    "    f.write(b'x')\n"
    "    f.close()\n"
    "    out['write'] = 'ok'\n"
    "except Exception as e:\n"
    "    out['write'] = type(e).__name__\n"
    "try:\n"
    "    import socket\n"
    "    s = socket.socket()\n"
    "    s.close()\n"
    "    out['socket'] = 'ok'\n"
    "except Exception as e:\n"
    "    out['socket'] = type(e).__name__\n"
    "print('PROBE:' + json.dumps(out))\n"
)


def _run_probe(monkeypatch, *, seccomp="on"):
    """Run the probe in a child process; return the parsed PROBE dict."""
    monkeypatch.setenv("PROGENITOR_SANDBOX_SECCOMP", seccomp)
    target_read = REPO_DIR / "README.md"
    target_write = Path(REPO_DIR.parent / "progenitor_escape_probe_should_not_exist")
    code = CTX.get_preexec_data() if False else None  # spawn/fork handled by Context
    q = CTX.Queue()
    p = CTX.Process(target=_probe_target, args=(str(HATCHERY), str(target_read), str(target_write), q))
    p.start()
    p.join(60)
    assert p.exitcode == 0, f"probe crashed: exitcode={p.exitcode}"
    line = q.get(timeout=10)
    assert line.startswith("PROBE:"), line
    return json.loads(line[6:])


def _probe_target(hatchery, read_path, write_path, q):
    import io, sys
    sys.path.insert(0, hatchery)
    buffer = io.StringIO()
    _stdout = sys.stdout
    sys.stdout = buffer
    try:
        exec(compile(PROBE_SRC.replace("sys.argv[1]", repr(hatchery))
                          .replace("sys.argv[2]", repr(read_path))
                          .replace("sys.argv[3]", repr(write_path)),
                     "<probe>", "exec"), {"__name__": "__probe__"})
    finally:
        sys.stdout = _stdout
        out = buffer.getvalue()
    for line in out.splitlines():
        if line.startswith("PROBE:"):
            q.put(line)
            return
    q.put("PROBE-MISSING:" + out[-200:])


def test_probe_read_ok_write_and_socket_blocked(tmp_path, monkeypatch):
    """Linux x86-64: reads pass, writes and sockets get EPERM under the filter."""
    if not (sys.platform == "linux" and platform.machine().lower() in ("x86_64", "amd64")):
        pytest.skip("seccomp hardening targets Linux x86-64")
    monkeypatch.delenv("PROGENITOR_SANDBOX_SECCOMP", raising=False)
    out = _run_probe(monkeypatch)
    assert out["hardening"]["applied"] is True, out
    assert out["read"] == "ok", out
    assert out["write"] == "PermissionError", out
    assert out["socket"] == "PermissionError", out


def test_probe_escape_hatch_disables_everything(tmp_path, monkeypatch):
    if not (sys.platform == "linux" and platform.machine().lower() in ("x86_64", "amd64")):
        pytest.skip("seccomp hardening targets Linux x86-64")
    monkeypatch.setenv("PROGENITOR_SANDBOX_SECCOMP", "off")
    out = _run_probe(monkeypatch)
    assert out["hardening"]["applied"] is False, out
    assert out["read"] == "ok" and out["write"] == "ok" and out["socket"] == "ok", out


def test_worker_smoke_benign_gene_reports_hardening(tmp_path, monkeypatch):
    """The wired _sandbox_worker still runs benign genes and reports its hardening state."""
    import engine

    class _Q:
        def __init__(self):
            self.items = []
        def put(self, item):
            self.items.append(item)

    monkeypatch.setattr(engine, "_GENE_EXEC_ALLOWED", True)
    monkeypatch.setenv("PROGENITOR_ALLOW_GENE_EXEC", "1")
    gene = tmp_path / "g.py"
    gene.write_text("def main():\n    return len([1, 2, 3])\n", encoding="utf-8", newline="")

    if sys.platform == "win32":
        # No seccomp on Windows -> nothing to leak into this process; call in-process.
        q = _Q()
        engine._sandbox_worker(q, str(gene), "main", {}, 50, 10)
        item = q.items[0]
    else:
        q = CTX.Queue()
        p = CTX.Process(target=engine._sandbox_worker, args=(q, str(gene), "main", {}, 50, 10))
        p.start()
        p.join(60)
        assert p.exitcode == 0, f"cage crashed: exitcode={p.exitcode}"
        item = q.get(timeout=10)

    assert item["status"] == "success", item
    assert item["result"] == 3
    assert isinstance(item.get("hardening"), dict)
