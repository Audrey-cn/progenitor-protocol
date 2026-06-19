"""F001: untrusted gene execution is refused unless the host opts in.

The in-process sandbox (restricted __builtins__ + AST denylist) is not a real security
boundary, so _sandbox_worker must refuse to exec gene code by default.
"""
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "hatchery"))

import engine


class _Queue:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


def test_exec_refused_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "_GENE_EXEC_ALLOWED", False)
    gene = tmp_path / "g.py"
    gene.write_text("def main():\n    return 1\n", encoding="utf-8")
    q = _Queue()
    engine._sandbox_worker(q, str(gene), "main", {}, 50, 5)
    assert q.items and q.items[0]["status"] == "exec_disabled"


def test_exec_runs_when_opted_in(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "_GENE_EXEC_ALLOWED", True)
    gene = tmp_path / "g.py"
    gene.write_text("def main():\n    return len([1, 2, 3])\n", encoding="utf-8")
    q = _Queue()
    engine._sandbox_worker(q, str(gene), "main", {}, 50, 5)
    assert q.items and q.items[0]["status"] == "success"
    assert q.items[0]["result"] == 3
