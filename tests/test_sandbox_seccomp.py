"""R4 Stage 1 - bisecting probe: variants in isolated children, one CI round."""
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
    "info = apply_sandbox_hardening(deny=(sys.argv[4] != 'minimal'), variant=sys.argv[4])\n"
    "out = {'hardening': info}\n"
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


def _probe_child(hatchery, read_path, write_path, variant, q):
    import io
    import sys as _sys
    _sys.path.insert(0, hatchery)
    buf = io.StringIO()
    old = _sys.stdout
    _sys.stdout = buf
    try:
        code = PROBE_SRC
        for pat, val in (("sys.argv[1]", hatchery), ("sys.argv[2]", read_path),
                         ("sys.argv[3]", write_path), ("sys.argv[4]", variant)):
            code = code.replace(pat, repr(val))
        exec(compile(code, "<probe>", "exec"), {"__name__": "__probe__"})
    finally:
        _sys.stdout = old
    for line in buf.getvalue().splitlines():
        if line.startswith("PROBE:"):
            q.put(line)
            return
    q.put("PROBE-MISSING:" + buf.getvalue()[-300:])


def _run_variant(variant, seccomp_env):
    read_path = REPO_DIR / "README.md"
    write_path = REPO_DIR.parent / "progenitor_escape_probe_should_not_exist"
    q = CTX.Queue()
    p = CTX.Process(target=_probe_child,
                    args=(str(HATCHERY), str(read_path), str(write_path), variant, q))
    p.start()
    p.join(60)
    assert p.exitcode == 0, f"probe crashed: exitcode={p.exitcode}"
    line = q.get(timeout=10)
    assert line.startswith("PROBE:"), line
    return json.loads(line[6:])


@pytest.mark.skipif(not LINUX_X64, reason="seccomp targets Linux x86-64")
def test_bisect_all_variants(tmp_path, monkeypatch):
    report = {}
    monkeypatch.delenv("PROGENITOR_SANDBOX_SECCOMP", raising=False)
    for variant in ("minimal", "socket-only", "full"):
        report[variant] = _run_variant(variant, seccomp_env="on")
    # 无过滤基线
    monkeypatch.setenv("PROGENITOR_SANDBOX_SECCOMP", "off")
    report["none"] = _run_variant("minimal", seccomp_env="off")
    print("BISECT:", json.dumps(report, indent=1))
    # 断言(带完整报告,失败时可见全部数据)
    assert report["none"]["read"] == "ok"
    assert report["minimal"]["read"] == "ok"
    assert report["socket-only"]["read"] == "ok", report
    assert report["socket-only"]["socket"] == "PermissionError"
    assert report["full"]["read"] == "ok", report
    assert report["full"]["write"] == "PermissionError"
    assert report["full"]["socket"] == "PermissionError"
