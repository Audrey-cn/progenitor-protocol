"""P1: LLM bridge — honest not_implemented + clean extension point.

Tests that:
- _llm_bridge_available() returns False by default
- phagocytize_and_evolve returns not_implemented when no bridge
- register_llm_bridge correctly wires a real bridge
- Old stub methods are removed
"""
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "hatchery"))

import engine


def test_llm_bridge_unavailable_by_default():
    """No bridge is registered — _llm_bridge_available returns False."""
    p = engine.Phagocyte()
    assert p._llm_bridge_available() is False


def test_llm_bridge_not_implemented_for_raw_text():
    """phagocytize_and_evolve with raw text returns not_implemented."""
    p = engine.Phagocyte()
    result = p.phagocytize_and_evolve(
        "some SOP text to absorb", target_type="raw"
    )
    assert result["status"] == "not_implemented"
    assert result["phase"] == "C.llm_bridge"
    assert "LLM bridge" in result["reason"]


def test_llm_bridge_not_implemented_for_url():
    """With raw type, phagocytize_and_evolve reaches the bridge check and returns not_implemented."""
    p = engine.Phagocyte()
    result = p.phagocytize_and_evolve(
        "some knowledge text", target_type="raw"
    )
    assert result["status"] == "not_implemented"
    assert "LLM bridge" in result["reason"]


def test_register_llm_bridge_makes_it_available():
    """register_llm_bridge sets the callable so _llm_bridge_available is True."""
    p = engine.Phagocyte()

    def fake_translate(text):
        return "def verify(): return True\n"

    p.register_llm_bridge(fake_translate)
    assert p._llm_bridge_available() is True
    assert p._llm_bridge is fake_translate


def test_register_llm_bridge_with_repair_fn():
    """register_llm_bridge also accepts an optional repair callable."""
    p = engine.Phagocyte()

    def fake_translate(text):
        return "def verify(): return True\n"

    def fake_repair(code, error):
        return "def verify(): return True\n"

    p.register_llm_bridge(fake_translate, repair_fn=fake_repair)
    assert p._llm_bridge_available() is True
    assert p._llm_bridge_repair is fake_repair


def test_stubs_are_removed():
    """The old stub methods no longer exist on Phagocyte."""
    p = engine.Phagocyte()
    assert not hasattr(p, "_llm_bridge_translate_stub")
    assert not hasattr(p, "_llm_bridge_repair_stub")
