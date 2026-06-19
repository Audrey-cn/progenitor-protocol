"""Regression tests for P0 network/validation hardening (F004/F005 + remote code scan).

- F005: content bytes must hash to the content-address (CID) BEFORE landing.
- F004: oversize payloads are refused before landing.
- Remote audit (`Phagocyte._crucible_remote`) now runs the lysosome code scan, so a
  downloaded gene carrying a denylisted call is rejected (previously it was not scanned).
"""
import hashlib
import os
import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "hatchery"))

import engine


# --- F005: verify content-addressing before landing ---

def test_land_rejects_content_address_mismatch():
    wrong_cid = "a" * 64  # well-formed sha256 that won't match the bytes
    with pytest.raises(RuntimeError):
        engine._land_content_before_ingest(b"hello world", wrong_cid)


def test_land_accepts_matching_content_address(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "LYSOSOME_DIR", str(tmp_path))
    data = b"benign gene bytes"
    cid = hashlib.sha256(data).hexdigest()
    path = engine._land_content_before_ingest(data, cid)
    assert os.path.isfile(path)


# --- F004: refuse oversize payloads before landing ---

def test_land_rejects_oversize(monkeypatch):
    monkeypatch.setattr(engine, "MAX_GENE_BYTES", 16)
    with pytest.raises(RuntimeError):
        engine._land_content_before_ingest(b"x" * 17, "not-a-sha256")


# --- Remote audit now scans downloaded gene code (lysosome) ---

def test_crucible_remote_blocks_dangerous_downloaded_gene(tmp_path):
    gene = tmp_path / "g.akashic_gene"
    gene.write_text(
        "# life_id: PGN@L1-G9-EVIL\n# creator: Attacker\n"
        "import os\ndef main():\n    os.system('rm -rf /')\n",
        encoding="utf-8",
    )
    assert engine.Phagocyte()._crucible_remote(str(gene)) is False


def test_crucible_remote_accepts_benign_downloaded_gene(tmp_path):
    gene = tmp_path / "g.akashic_gene"
    gene.write_text(
        "# life_id: PGN@L1-G1-OK\n# creator: Audrey\ndef main():\n    return 42\n",
        encoding="utf-8",
    )
    assert engine.Phagocyte()._crucible_remote(str(gene)) is True
