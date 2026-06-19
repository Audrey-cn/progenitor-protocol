"""Regression tests for the hardened module-level engine.crucible_audit().

Covers two fixes:
  1. The lineage regex now matches the real comment-style header (# life_id: PGN@...),
     not only the quoted YAML form.
  2. crucible_audit now runs the lysosome dangerous-pattern denylist, so a gene
     carrying os.system / eval / subprocess / ... is rejected regardless of lineage.
"""
import sys
import tempfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
HATCHERY_DIR = REPO_DIR / "hatchery"
sys.path.insert(0, str(HATCHERY_DIR))

import engine


def _write_gene(text):
    f = tempfile.NamedTemporaryFile("w", suffix="", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return f.name


def test_accepts_benign_gene_with_unquoted_lineage():
    # The real registry format uses an unquoted comment header.
    path = _write_gene(
        "# life_id: PGN@L1-G1-DEMO\n# creator: Audrey\n# description: benign demo\n\n"
        "def main():\n    return sum(range(10))\n"
    )
    assert engine.crucible_audit(path) is True


def test_blocks_os_system_gene():
    path = _write_gene(
        "# life_id: PGN@L1-G9-EVIL\n# creator: Attacker\n\n"
        "import os\ndef main():\n    os.system('rm -rf /')\n"
    )
    assert engine.crucible_audit(path) is False


def test_blocks_eval_gene():
    path = _write_gene("# life_id: PGN@L1-G9-EVAL\n\ndef main():\n    return eval('1 + 1')\n")
    assert engine.crucible_audit(path) is False


def test_blocks_subprocess_gene():
    path = _write_gene(
        "# life_id: PGN@L1-G9-SHELL\n\nimport subprocess\n"
        "def main():\n    subprocess.run(['ls'])\n"
    )
    assert engine.crucible_audit(path) is False


def test_missing_file_is_rejected():
    assert engine.crucible_audit("/nonexistent/path/to/gene") is False
