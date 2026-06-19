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


# --- F001: denylist hardening — sandbox-escape gadgets must be rejected ---

def test_blocks_getattr_obfuscated_os_system():
    path = _write_gene(
        "# life_id: PGN@L1-G9-OBF\nimport os\n"
        "def main():\n    return getattr(os, 'sys' + 'tem')('id')\n"
    )
    assert engine.crucible_audit(path) is False


def test_blocks_subclasses_walk_escape():
    path = _write_gene(
        "# life_id: PGN@L1-G9-ESC\n"
        "def main():\n    return ().__class__.__base__.__subclasses__()\n"
    )
    assert engine.crucible_audit(path) is False


def test_blocks_builtins_subscript():
    path = _write_gene(
        "# life_id: PGN@L1-G9-BIN\n"
        "def main():\n    return __builtins__['eval']('1+1')\n"
    )
    assert engine.crucible_audit(path) is False


# --- F002: GPG signature verification must FAIL CLOSED on error in strict mode ---

def test_signature_fails_closed_on_error_in_strict(monkeypatch, tmp_path):
    import subprocess
    gene = tmp_path / "g.pgn"
    gene.write_text("# life_id: PGN@L1-G1-X\n# creator: Audrey\n", encoding="utf-8")
    (tmp_path / "g.pgn.sig").write_text("dummy-sig", encoding="utf-8")
    monkeypatch.setattr(engine, "SIGNER_FINGERPRINTS", ["DEADBEEF"])
    monkeypatch.setattr(engine, "SIGNATURE_MODE", "strict")
    monkeypatch.setattr(engine, "SIGNATURE_REQUIRED", True)

    def boom(*a, **k):
        raise RuntimeError("gpg exploded")

    monkeypatch.setattr(subprocess, "run", boom)
    assert engine._verify_digital_signature(str(gene), is_internal=False) is False


def test_signature_skipped_when_no_fingerprints(monkeypatch, tmp_path):
    gene = tmp_path / "g.pgn"
    gene.write_text("x", encoding="utf-8")
    monkeypatch.setattr(engine, "SIGNER_FINGERPRINTS", [])
    assert engine._verify_digital_signature(str(gene), is_internal=True) is True
