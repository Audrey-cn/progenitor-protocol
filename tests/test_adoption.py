"""Voluntary adoption pipeline — inspect → decide → adopt, no auto-infect (Iteration 3)."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hatchery"))
import adoption  # noqa: E402
import engine  # noqa: E402

PURE_GENE = b"# purity: pure\ndef main(x):\n    return x * 2\n"
EFFECTFUL_GENE = b"# purity: effectful\n# grants: [fs:write]\ndef main():\n    return 1\n"


def _entry_for(gene_bytes, **over):
    e = {"capability": "demo", "creator": "Audrey", "trust_state": "registry_verified",
         "content_sha256": hashlib.sha256(gene_bytes).hexdigest()}
    e.update(over)
    return e


# --- inspect -------------------------------------------------------------------------------

def test_inspect_reads_provenance_and_scope():
    p = adoption.inspect(PURE_GENE, index_entry=_entry_for(PURE_GENE), source="peer://x")
    assert p["purity"] == "pure"
    assert p["trust_state"] == "registry_verified"
    assert p["hash_verified"] is True
    assert p["source"] == "peer://x"


def test_inspect_flags_hash_mismatch():
    p = adoption.inspect(PURE_GENE, expected_sha256="0" * 64)
    assert p["hash_verified"] is False


# --- decide (advisory) ---------------------------------------------------------------------

def test_decide_adopt_for_trusted_pure():
    p = adoption.inspect(PURE_GENE, index_entry=_entry_for(PURE_GENE))
    assert adoption.decide(p)["recommend"] == "adopt"


def test_decide_rejects_hash_mismatch():
    p = adoption.inspect(PURE_GENE, expected_sha256="0" * 64)
    assert adoption.decide(p)["recommend"] == "reject"


def test_decide_rejects_invalid_signature():
    p = adoption.inspect(PURE_GENE, index_entry=_entry_for(PURE_GENE, trust_state="creator-signature-invalid"))
    assert adoption.decide(p)["recommend"] == "reject"


def test_decide_rejects_flagged_reputation():
    p = adoption.inspect(PURE_GENE, index_entry=_entry_for(PURE_GENE))
    assert adoption.decide(p, reputation="flagged")["recommend"] == "reject"


def test_decide_asks_for_effectful_with_grants():
    p = adoption.inspect(EFFECTFUL_GENE, index_entry=_entry_for(EFFECTFUL_GENE))
    out = adoption.decide(p)
    assert out["recommend"] == "ask"
    assert any("grants" in r for r in out["reasons"])


def test_decide_asks_for_untrusted_provenance():
    p = adoption.inspect(PURE_GENE, index_entry=_entry_for(PURE_GENE, trust_state="unverified"))
    assert adoption.decide(p)["recommend"] == "ask"


# --- adopt (host decides; never executes) --------------------------------------------------

def test_adopt_refused_without_approval(tmp_path):
    p = adoption.inspect(PURE_GENE, index_entry=_entry_for(PURE_GENE))
    out = adoption.adopt(p, PURE_GENE, tmp_path / "cache", approved=False)
    assert out["status"] == "refused"
    assert not (tmp_path / "cache").exists() or not list((tmp_path / "cache").iterdir())


def test_adopt_caches_on_approval(tmp_path):
    p = adoption.inspect(PURE_GENE, index_entry=_entry_for(PURE_GENE))
    out = adoption.adopt(p, PURE_GENE, tmp_path / "cache", approved=True)
    assert out["status"] == "adopted"
    cached = Path(out["path"])
    assert cached.exists() and cached.read_bytes() == PURE_GENE
    assert cached.name == hashlib.sha256(PURE_GENE).hexdigest()


def test_adopt_detects_tampered_bytes(tmp_path):
    p = adoption.inspect(PURE_GENE, index_entry=_entry_for(PURE_GENE))
    out = adoption.adopt(p, PURE_GENE + b"# tampered\n", tmp_path / "cache", approved=True)
    assert out["status"] == "hash_mismatch"


# --- engine wiring -------------------------------------------------------------------------

def test_phagocyte_propose_and_adopt(tmp_path):
    phg = engine.Phagocyte()
    proposed = phg.propose_adoption(PURE_GENE, index_entry=_entry_for(PURE_GENE), source="peer://y")
    assert proposed["recommendation"]["recommend"] == "adopt"
    # nothing cached yet — host must approve
    out = phg.adopt_gene(proposed["proposal"], PURE_GENE, approved=True, cache_dir=str(tmp_path / "c"))
    assert out["status"] == "adopted"
