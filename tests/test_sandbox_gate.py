"""F001: untrusted gene execution is refused unless the host opts in.

The in-process sandbox (restricted __builtins__ + AST denylist) is not a real security
boundary, so _sandbox_worker must refuse to exec gene code by default.

Both tests run the worker in a CHILD process, matching production usage - an in-process
call would install the R4 seccomp filter inside the pytest process (leak) on Linux.
"""
import json
import multiprocessing
import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "hatchery"))

CTX = multiprocessing.get_context("spawn" if sys.platform == "win32" else "fork")


def _run_worker(tmp_path, monkeypatch, gene_code, opt_in):
    import engine
    monkeypatch.setattr(engine, "_GENE_EXEC_ALLOWED", opt_in)
    monkeypatch.setenv("PROGENITOR_ALLOW_GENE_EXEC", "1" if opt_in else "0")
    gene = tmp_path / "g.py"
    gene.write_text(gene_code, encoding="utf-8", newline="")
    q = CTX.Queue()
    p = CTX.Process(target=engine._sandbox_worker, args=(q, str(gene), "main", {}, 50, 10))
    p.start()
    p.join(60)
    assert p.exitcode == 0, f"cage crashed: exitcode={p.exitcode}"
    return q.get(timeout=10)


def test_exec_refused_by_default(tmp_path, monkeypatch):
    item = _run_worker(tmp_path, monkeypatch, "def main():\n    return 1\n", opt_in=False)
    assert item["status"] == "exec_disabled"


def test_exec_runs_when_opted_in(tmp_path, monkeypatch):
    item = _run_worker(tmp_path, monkeypatch, "def main():\n    return len([1, 2, 3])\n", opt_in=True)
    assert item["status"] == "success"
    assert item["result"] == 3
