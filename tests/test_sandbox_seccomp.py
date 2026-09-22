"""R4 Stage 1 - seccomp network+exec denial probes (Linux x86-64, verified on ubuntu CI).

Each probe runs in a freshly spawned child (clean glibc init, no inherited filter), installs
one filter variant, and reports syscall outcomes. The gene sandbox itself uses compute-only
restricted builtins, so the kernel filter is defense against ESCAPES (Stage 1 scope: network
+ exec; FS scoping = Stage 2 Landlock).
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
    "out = {'hardening': apply_sandbox_hardening(variant=sys.argv[4])}\n"
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
def test_probe_variants(tmp_path, monkeypatch):
    monkeypatch.delenv("PROGENITOR_SANDBOX_SECCOMP", raising=False)
    read_path = REPO_DIR / "README.md"
    write_path = REPO_DIR.parent / "progenitor_escape_probe_should_not_exist"
    report = {}
    for variant in ("minimal", "socket-only", "full"):
        q = CTX.Queue()
        p = CTX.Process(target=_probe_child,
                        args=(str(HATCHERY), str(read_path), str(write_path), variant, q))
        p.start()
        p.join(60)
        assert p.exitcode == 0, f"{variant}: probe crashed exitcode={p.exitcode}"
        line = q.get(timeout=10)
        assert line.startswith("PROBE:"), f"{variant}: {line}"
        report[variant] = json.loads(line[6:])
    print("PROBE-REPORT:", json.dumps(report, indent=1))
    # minimal: arch check + allow-all -> no restriction
    assert report["minimal"]["socket"] == "ok" and report["minimal"]["read"] == "ok"
    # socket-only / full: network blocked, reads+writes untouched
    for variant in ("socket-only", "full"):
        assert report[variant]["socket"] == "PermissionError", report[variant]
        assert report[variant]["read"] == "ok", report[variant]
        assert report[variant]["write"] == "ok", report[variant]


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
