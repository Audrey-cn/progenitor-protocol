"""R4 Stage 1 - in-CI filter diagnosis: stack RET-terminated prefixes, find the first EINVAL."""
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


def _diag_child(hatchery, q):
    import io
    import sys as _sys
    _sys.path.insert(0, hatchery)
    buf = io.StringIO()
    old = _sys.stdout
    _sys.stdout = buf
    try:
        import sandbox_linux
        results = sandbox_linux.diagnose_filter()
        print("DIAG:" + json.dumps(results))
        # 探针: 全过滤器安装失败后,进程是无过滤的 → 三个探针都应该 ok
        info = sandbox_linux.apply_sandbox_hardening()
        probes = {}
        with open(REPO_DIR / "README.md", "rb") as f:
            f.read(8)
        probes["read"] = "ok"
        try:
            f = open("/tmp/progenitor_probe_write", "wb")
            f.write(b"x")
            f.close()
            probes["write"] = "ok"
        except Exception as e:
            probes["write"] = type(e).__name__
        try:
            import socket
            s = socket.socket()
            s.close()
            probes["socket"] = "ok"
        except Exception as e:
            probes["socket"] = type(e).__name__
        print("POSTDIAG:" + json.dumps({"info": info, "probes": probes}))
    finally:
        _sys.stdout = old
        out = buf.getvalue()
    for marker in ("DIAG:", "POSTDIAG:"):
        for line in out.splitlines():
            if line.startswith(marker):
                q.put(line)


def test_diagnose(tmp_path, monkeypatch):
    if not (sys.platform == "linux" and platform.machine().lower() in ("x86_64", "amd64")):
        pytest.skip("seccomp targets Linux x86-64")
    monkeypatch.delenv("PROGENITOR_SANDBOX_SECCOMP", raising=False)
    q = CTX.Queue()
    p = CTX.Process(target=_diag_child, args=(str(HATCHERY), q))
    p.start()
    p.join(60)
    collected = {}
    while True:
        try:
            line = q.get(timeout=10)
        except Exception:
            break
        collected.setdefault(line[:5], line)
    for k in ("DIAG:", "POSTDIAG:"):
        v = collected.get(k)
        print(k, "->", v)
        assert v is not None, f"missing {k} output"
