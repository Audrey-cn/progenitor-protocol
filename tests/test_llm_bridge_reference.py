"""R5: reference LLM bridge — end-to-end absorb-from-knowledge tests.

Proves the extension point completes the real pipeline: register bridge ->
phagocytize_and_evolve(raw) -> lysosome -> sandbox (verify self-check) ->
crystallization -> evolution_complete.
"""
import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "hatchery"))
sys.path.insert(0, str(REPO_DIR / "examples"))

import engine  # noqa: E402
import llm_bridge_reference as lbr  # noqa: E402


SPEC_OK = (
    '{"name": "contrib-flow-check",'
    ' "description": "absorb a tiny deterministic capability",'
    ' "body": "return \'absorbed:42\'",'
    ' "verify": "return main() == \'absorbed:42\'"}'
)


def _phagocyte():
    return engine.Phagocyte()


def test_spec_bridge_passes_lysosome(tmp_path):
    code = lbr.spec_to_gene_code(SPEC_OK)
    p = _phagocyte()
    audit = p.crucible._layer4_lysosome(code)
    assert audit["passed"] is True, audit


def test_e2e_spec_bridge_evolution_complete(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # crystallization artifacts stay in the sandbox
    p = _phagocyte()
    p.register_llm_bridge(lbr.spec_to_gene_code)
    result = p.phagocytize_and_evolve(SPEC_OK, target_type="raw")
    assert result["status"] == "evolution_complete", result
    assert result["crystallized_seed"]["code"], result
    # the crystallized seed carries the absorbed logic
    assert "absorbed" in result["crystallized_seed"]["code"]


def test_make_llm_bridge_wraps_chat_callable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = _phagocyte()
    calls = []

    def fake_llm(prompt):
        calls.append(prompt)
        assert "verify()" in prompt  # the prompt states the sandbox contract
        return "def main():\n    return 1\n\ndef verify():\n    return True\n"

    translate, repair = lbr.make_llm_bridge(fake_llm)
    p.register_llm_bridge(translate, repair)
    result = p.phagocytize_and_evolve("some knowledge text", target_type="raw")
    assert result["status"] == "evolution_complete", result
    assert calls, "LLM was never consulted"


def test_repair_loop_recovers_from_bad_first_draft(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = _phagocyte()
    attempts = []

    def flaky_llm(prompt):
        attempts.append(prompt)
        if len(attempts) == 1:
            # first draft is rejected: verify() returns False
            return "def main():\n    return 1\n\ndef verify():\n    return False\n"
        return "def main():\n    return 1\n\ndef verify():\n    return True\n"

    repair_calls = []

    def flaky_repair(code, error):
        repair_calls.append(error)
        return "def main():\n    return 1\n\ndef verify():\n    return True\n"

    translate, repair = lbr.make_llm_bridge(flaky_llm, repair_chat=flaky_repair)
    p.register_llm_bridge(translate, repair)
    result = p.phagocytize_and_evolve("knowledge", target_type="raw")
    assert result["status"] == "evolution_complete", result
    # first draft failed the verify self-check; the repair callable fixed it without
    # consulting the LLM again (repair_chat is a separate callable by contract).
    assert len(attempts) == 1
    assert len(repair_calls) == 1 and "沙盒自检逻辑未通过" in repair_calls[0]


def test_dangerous_spec_rejected_by_lysosome(tmp_path, monkeypatch):
    p = _phagocyte()
    p.register_llm_bridge(lbr.spec_to_gene_code)
    bad_spec = (
        '{"name": "bad", "description": "tries to escape the sandbox",'
        ' "body": "import os\\nresult = os.getcwd()"}'
    )
    result = p.phagocytize_and_evolve(bad_spec, target_type="raw")
    assert result["status"] == "dead", result
    assert result["phase"] == "C.sandbox_lysosome", result
