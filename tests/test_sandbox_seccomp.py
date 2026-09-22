"""R4 Stage 1 - diagnostic variants, all collected even if one child dies."""
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
    "info = apply_sandbox_hardening(variant=sys.argv[4])\n"
    "out = {'hardening': {'applied': info.get('applied'), 'variant': info.get('variant', sys.argv[4])}}\n"
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
    except Exception as e:
        buf.write("\nPROBE-EXC:" + repr(e))
    finally:
        _sys.stdout = old
    for line in buf.getvalue().splitlines():
        if line.startswith(("PROBE:", "PROBE-EXC:")):
            q.put(line)
            return


@pytest.mark.skipif(not LINUX_X64, reason="seccomp targets Linux x86-64")
def test_diagnostic_variants(tmp_path, monkeypatch):
    monkeypatch.delenv("PROGENITOR_SANDBOX_SECCOMP", raising=False)
    read_path = REPO_DIR / "README.md"
    write_path = REPO_DIR.parent / "progenitor_escape_probe_should_not_exist"
    report = {}
    for variant in ("diag-openat-any", "diag-openat-writeflag", "diag-arch-match"):
        q = CTX.Queue()
        p = CTX.Process(target=_probe_child,
                        args=(str(HATCHERY), str(read_path), str(write_path), variant, q))
        p.start()
        p.join(60)
        if p.exitcode != 0:
            report[variant] = {"crashed": True, "exitcode": p.exitcode}
            q.close()
            continue
        try:
            line = q.get(timeout=10)
        except Exception:
            report[variant] = {"crashed": True}
            continue
        assert line.startswith("PROBE:"), f"{variant}: {line}"
        report[variant] = json.loads(line[6:])
    print("DIAG-REPORT:", json.dumps(report, indent=1))
    # Stage-1 语义断言(full = socket+exec 拒绝;FS 写限定归 Stage 2 Landlock):
    # none      : 全部 ok(基线)
    # minimal   : 全部 ok(编码+arch+安装验证)
    # socket-only: read ok / socket EPERM(每 syscall 匹配验证)
    # full      : read ok / write ok / socket EPERM(网络+exec 拒绝,无 FS 限定)
    assert report["none"]["read"] == "ok" and report["none"]["socket"] == "ok", report["none"]
    assert report["minimal"]["applied"] is True and report["minimal"]["read"] == "ok", report["minimal"]
    assert report["socket-only"]["read"] == "ok", report["socket-only"]
    assert report["socket-only"]["socket"] == "PermissionError", report["socket-only"]
    assert report["full"]["read"] == "ok", report["full"]
    assert report["full"]["write"] == "ok", report["full"]
    assert report["full"]["socket"] == "PermissionError", report["full"]
