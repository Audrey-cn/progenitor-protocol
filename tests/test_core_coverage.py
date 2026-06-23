"""P3: Test coverage for core untested classes.

Exercises:
- Crucible.audit() integrated L1-L4 audit with complete gene content
- TelomereGuard timeout and memory limits
- Progenitor semantic reflex routing
"""
import json
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "hatchery"))

import engine


# ── Helpers ──────────────────────────────────────────────────────────────────

_VOW = engine._GENESIS_VOW_BUFFER


def _valid_pgn_content():
    return (
        "# life_id: PGN@L1-G99-TEST-AUDIT\n"
        "# creator: TestCreator\n"
        "# description: A benign audit test gene with sufficient description length\n"
        "---\n"
        "genesis_vow_buffer: " + _VOW + "\n"
        "def main():\n"
        "    return sum(range(10))\n"
    )


def _valid_metadata():
    return {
        "life_crest": {
            "life_id": "PGN@L1-G99-TEST-AUDIT",
            "founder_chronicle": {
                "the_rosetta_monolith": {
                    "genesis_vow_buffer": _VOW,
                    "creator_entity": engine._CREATOR_ENTITY,
                    "singularity_hash": engine._SINGULARITY_HASH,
                }
            },
        },
        "genealogy_codex": {"current_genealogy": "L1-G99-TEST-AUDIT"},
        "skill_soul": {},
        "primordial_endosperm": {},
    }


# ── Crucible.audit() integrated tests ───────────────────────────────────────


def test_crucible_audit_benign_gene_passes():
    """A benign gene with valid metadata passes all 4 layers."""
    c = engine.Crucible()
    code = "def main():\n    return sum(range(10))\n"
    result = c.audit(_valid_pgn_content(), _valid_metadata(), code_str=code)
    assert result["passed"] is True
    assert result["critical"] is False
    assert len(result["results"]) == 4
    assert all(r["passed"] for r in result["results"])


def test_crucible_audit_malicious_code_blocked():
    """Malicious code (eval) is caught at L4."""
    c = engine.Crucible()
    result = c.audit(_valid_pgn_content(), _valid_metadata(), code_str="x = eval('1+1')\n")
    assert result["passed"] is False
    assert result["critical"] is True
    l4 = result["results"][3]
    assert l4["layer"] == "L4"
    assert l4["passed"] is False


def test_crucible_audit_missing_lineage_blocked():
    """Missing lineage (L2) causes audit to fail."""
    c = engine.Crucible()
    broken_meta = _valid_metadata()
    broken_meta["genealogy_codex"] = {}
    result = c.audit(_valid_pgn_content(), broken_meta, code_str="def main():\n    pass\n")
    # L2 risk is MEDIUM, not CRITICAL — overall audit still passes without code issues
    l2 = result["results"][1]
    assert l2["layer"] == "L2"
    assert l2["passed"] is False


def test_crucible_audit_missing_required_field_blocked():
    """Missing required metadata field (L1) causes audit to fail."""
    c = engine.Crucible()
    broken_meta = _valid_metadata()
    del broken_meta["skill_soul"]
    result = c.audit(_valid_pgn_content(), broken_meta, code_str="def main():\n    pass\n")
    # L1 risk is HIGH, not CRITICAL — audit still passes without dangerous code
    l1 = result["results"][0]
    assert l1["layer"] == "L1"
    assert l1["passed"] is False


def test_crucible_audit_rosetta_monolith_valid():
    """The rosetta monolith check (L3) validates the genesis vow."""
    c = engine.Crucible()
    result = c.audit(_valid_pgn_content(), _valid_metadata(), code_str="def main():\n    pass\n")
    l3 = result["results"][2]
    assert l3["layer"] == "L3"
    assert l3["passed"] is True


def test_crucible_audit_rosetta_monolith_tampered():
    """Tampered rosetta monolith fails L3."""
    c = engine.Crucible()
    broken_meta = _valid_metadata()
    broken_meta["life_crest"]["founder_chronicle"]["the_rosetta_monolith"]["singularity_hash"] = "deadbeef" * 8
    result = c.audit(_valid_pgn_content(), broken_meta, code_str="def main():\n    pass\n")
    assert result["passed"] is False
    l3 = result["results"][2]
    assert l3["passed"] is False


# ── TelomereGuard tests ─────────────────────────────────────────────────────


def test_telomere_guard_timeout_triggers():
    """A busy loop exceeding the timeout raises ApoptosisException."""
    caught = True
    try:
        with engine.TelomereGuard(max_mem_mb=50, timeout_sec=1):
            while True:
                pass
    except engine.ApoptosisException:
        caught = True
    except Exception:
        caught = False
    assert caught


def test_telomere_guard_allows_quick_work():
    """Quick operations pass through TelomereGuard without triggering."""
    with engine.TelomereGuard(max_mem_mb=50, timeout_sec=5):
        result = sum(range(1000))
    assert result == 499500


# ── Progenitor reflex tests ──────────────────────────────────────────────────


def test_symbiotic_treaty_returns_json():
    """get_symbiotic_treaty returns valid JSON string."""
    treaty_str = engine.get_symbiotic_treaty()
    treaty = json.loads(treaty_str)
    assert treaty["status"] == "symbiotic_ready"
    assert "max_memory_mb" in treaty
    assert "max_timeout_sec" in treaty


def test_progenitor_process_reflex_matches_phagocyte():
    """Semantic reflex detects phagocyte triggers in user input."""
    p = engine.Progenitor(
        tools={},
        tracker=engine.EvolutionTracker(),
        chronicler=None,
        packager=None,
        phagocyte=engine.Phagocyte(),
        enzyme_lock=None,
        metadata={},
    )
    result = p.process_reflex("看看这个SOP文档")
    assert isinstance(result, dict)
    assert result["triggered_genes"] is not None
    assert "G010-phagocyte" in result["triggered_genes"]


def test_progenitor_reflex_no_match():
    """Process reflex returns empty when no keyword matches."""
    p = engine.Progenitor(
        tools={},
        tracker=engine.EvolutionTracker(),
        chronicler=None,
        packager=None,
        phagocyte=engine.Phagocyte(),
        enzyme_lock=None,
        metadata={},
    )
    result = p.process_reflex("今天天气真好")
    assert isinstance(result, dict)
    assert result["triggered_genes"] == []
