"""Security tests for the REAL engine.Crucible class.

Previously this file re-implemented its own crucible_* helpers and never imported the
engine, so it tested a fiction. It now exercises engine.Crucible directly — the actual
security auditor used at ingestion — covering L1 integrity, L2 lineage, and the L4
lysosome denylist (incl. the hardened escape-gadget detection and host-injected rules).
"""
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "hatchery"))

import engine


def _complete_metadata():
    return {
        "life_crest": {"life_id": "PGN@L1-G1-TEST"},
        "genealogy_codex": {"current_genealogy": "L1-G1-TEST"},
        "skill_soul": {},
        "primordial_endosperm": {},
    }


class TestCrucibleLayer1Integrity:
    def test_complete_metadata_passes(self):
        assert engine.Crucible()._layer1_integrity(_complete_metadata())["passed"] is True

    def test_missing_field_fails(self):
        meta = _complete_metadata()
        del meta["skill_soul"]
        result = engine.Crucible()._layer1_integrity(meta)
        assert result["passed"] is False
        assert "skill_soul" in result["reason"]


class TestCrucibleLayer2Lineage:
    def test_genealogy_present_passes(self):
        assert engine.Crucible()._layer2_lineage(_complete_metadata())["passed"] is True

    def test_missing_genealogy_fails(self):
        assert engine.Crucible()._layer2_lineage({"genealogy_codex": {}})["passed"] is False


class TestCrucibleLayer4Lysosome:
    def test_benign_code_passes(self):
        assert engine.Crucible()._layer4_lysosome("def main():\n    return sum(range(10))\n")["passed"] is True

    def test_os_system_blocked(self):
        assert engine.Crucible()._layer4_lysosome("import os\nos.system('id')\n")["passed"] is False

    def test_eval_blocked(self):
        assert engine.Crucible()._layer4_lysosome("x = eval('1+1')\n")["passed"] is False

    def test_subprocess_blocked(self):
        assert engine.Crucible()._layer4_lysosome("import subprocess\nsubprocess.run(['ls'])\n")["passed"] is False

    def test_obfuscated_getattr_blocked(self):
        # hardened: split-string getattr must not slip past the denylist
        assert engine.Crucible()._layer4_lysosome("import os\ngetattr(os, 'sys' + 'tem')('id')\n")["passed"] is False

    def test_subclasses_walk_blocked(self):
        assert engine.Crucible()._layer4_lysosome("().__class__.__base__.__subclasses__()\n")["passed"] is False

    def test_builtins_subscript_blocked(self):
        assert engine.Crucible()._layer4_lysosome("__builtins__['eval']('1')\n")["passed"] is False

    def test_syntax_error_rejected(self):
        assert engine.Crucible()._layer4_lysosome("def main(:\n    pass\n")["passed"] is False

    def test_host_injected_blacklist(self):
        # a host can extend the denylist via host_rules; a plain Crucible should not block it
        hardened = engine.Crucible(host_rules={"additional_blacklist": ["my_risky_call"]})
        assert hardened._layer4_lysosome("my_risky_call()\n")["passed"] is False
        assert engine.Crucible()._layer4_lysosome("my_risky_call()\n")["passed"] is True
