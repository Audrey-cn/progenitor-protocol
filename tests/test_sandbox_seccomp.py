"""R4 Stage 1 - seccomp-BPF hardening probe tests (Linux x86-64, verified on ubuntu CI).

Bisecting probe: each variant runs in its own child process so the kernel filter never
leaks into pytest. Reports every syscall outcome in the assertion messages.
"""
import json
import multiprocessing
import platform
import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
HATCHERY = REPO_DIR / "hatchery"
LINUX_X64 = sys.platform == "linux" and platform.machine().lower() in ("x86_64", "amd64")
CTX = multiprocessing.get_context("spawn" if sys.platform == "win32" else "fork")

PROBE_SRC = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from sandbox_linux import apply_sandbox_hardening\n"
    "deny = sys.argv[4] == '1'\n"
    "out = {'hardening': apply_sandbox_hardening(deny=deny)}\n"
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


def _probe_child(hatchery, read_path, write_path, deny, q):
    import io
    import sys as _sys
    _sys.path.insert(0, hatchery)
    buf = io.StringIO()
    old = _sys.stdout
    _sys.stdout = buf
    try:
        code = PROBE_SRC.replace("sys.argv[1]", repr(hatchery))
        code = code.replace("sys.argv[2]", repr(read_path))
        code = code.replace("sys.argv[3]", repr(write_path))
        code = code.replace("sys.argv[4]", repr("1" if deny else "0"))
        exec(compile(code, "<probe>", "exec"), {"__name__": "__probe__"})
    finally:
        _sys.stdout = old
    for line in buf.getvalue().splitlines():
        if line.startswith("PROBE:"):
            q.put(line)
            return
    q.put("PROBE-MISSING:" + buf.getvalue()[-300:])


def _run_probe(monkeypatch, deny=True, seccomp_env="on"):
    monkeypatch.setenv("PROGENITOR_SANDBOX_SECCOMP", seccomp_env)
    read_path = REPO_DIR / "README.md"
    write_path = REPO_DIR.parent / "progenitor_escape_probe_should_not_exist"
    q = CTX.Queue()
    p = CTX.Process(target=_probe_child,
                    args=(str(HATCHERY), str(read_path), str(write_path), deny, q))
    p.start()
    p.join(60)
    assert p.exitcode == 0, f"probe crashed: exitcode={p.exitcode}"
    line = q.get(timeout=10)
    assert line.startswith("PROBE:"), line
    return json.loads(line[6:])


@pytest.mark.skipif(not LINUX_X64, reason="seccomp targets Linux x86-64")
def test_no_filter_baseline_clean(tmp_path, monkeypatch):
    out = _run_probe(monkeypatch, deny=False, seccomp_env="off")
    assert out == {"hardening": {"applied": False, "reason": "disabled via PROGENITOR_SANDBOX_SECCOMP"},
                   "read": "ok", "write": "ok", "socket": "ok"}, out


@pytest.mark.skipif(not LINUX_X64, reason="seccomp targets Linux x86-64")
def test_minimal_filter_allows_everything(tmp_path, monkeypatch):
    """arch-check + unconditional allow: must NOT restrict anything."""
    monkeypatch.delenv("PROGENITOR_SANDBOX_SECCOMP", raising=False)
    out = _run_probe(monkeypatch, deny=False)
    assert out["hardening"]["applied"] is True, out
    assert out["read"] == "ok", out
    assert out["write"] == "ok", out
    assert out["socket"] == "ok", out


@pytest.mark.skipif(not LINUX_X64, reason="seccomp targets Linux x86-64")
def test_full_filter_blocks_write_and_socket_allows_read(tmp_path, monkeypatch):
    monkeypatch.delenv("PROGENITOR_SANDBOX_SECCOMP", raising=False)
    out = _run_probe(monkeypatch, deny=True)
    assert out["hardening"]["applied"] is True, out
    assert out["read"] == "ok", out
    assert out["write"] == "PermissionError", out
    assert out["socket"] == "PermissionError", out
