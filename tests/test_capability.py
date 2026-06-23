"""Gene Contract v2 — capability manifest + pure/advisory scoped execution (docs/VISION.md)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hatchery"))
import capability as cap  # noqa: E402


# --- AST allowlist: accepts safe compute ---------------------------------------------------

def test_pure_safe_accepts_benign_compute():
    ok, _ = cap.check_pure_safe("def main(x):\n    return x * 2 + sum(range(x))\n")
    assert ok is True


def test_pure_safe_accepts_whitelisted_import():
    ok, _ = cap.check_pure_safe("import json\ndef main():\n    return json.dumps({'a': 1})\n")
    assert ok is True


# --- AST allowlist: rejects ambient authority + escape gadgets -----------------------------

def test_pure_safe_rejects_os_import():
    ok, reason = cap.check_pure_safe("import os\ndef main():\n    return os.getcwd()\n")
    assert ok is False and "import" in reason


def test_pure_safe_rejects_from_import():
    ok, _ = cap.check_pure_safe("from subprocess import run\ndef main():\n    return run(['ls'])\n")
    assert ok is False


def test_pure_safe_rejects_getattr_call():
    ok, _ = cap.check_pure_safe("def main():\n    return getattr(1, 'real')\n")
    assert ok is False


def test_pure_safe_rejects_dunder_walk():
    ok, _ = cap.check_pure_safe("def main():\n    return ().__class__.__bases__\n")
    assert ok is False


def test_pure_safe_rejects_builtins_subscript():
    ok, _ = cap.check_pure_safe("def main():\n    return __builtins__['eval']('1')\n")
    assert ok is False


def test_pure_safe_rejects_eval_call():
    ok, _ = cap.check_pure_safe("def main():\n    return eval('1 + 1')\n")
    assert ok is False


# --- pure/advisory execution ---------------------------------------------------------------

def test_run_pure_gene_proposes_result():
    out = cap.run_pure_gene("def main(x):\n    return x * 3\n", {"x": 7})
    assert out["status"] == "proposed" and out["advisory"] is True and out["result"] == 21


def test_run_pure_gene_with_whitelisted_module():
    out = cap.run_pure_gene("import json\ndef main():\n    return json.dumps({'k': 1})\n")
    assert out["status"] == "proposed" and out["result"] == '{"k": 1}'


def test_run_pure_gene_refuses_unsafe_code():
    out = cap.run_pure_gene("import os\ndef main():\n    return os.getcwd()\n")
    assert out["status"] == "rejected"


def test_run_pure_gene_blocks_runtime_import_escape():
    # belt-and-suspenders: the __import__() call is denied at the AST level
    out = cap.run_pure_gene("def main():\n    return __import__('os').getcwd()\n")
    assert out["status"] in ("rejected", "error")


def test_run_pure_gene_missing_entry():
    out = cap.run_pure_gene("x = 1\n")
    assert out["status"] == "loaded"


def test_run_pure_gene_times_out_on_runaway_loop():
    out = cap.run_pure_gene("def main():\n    while True:\n        pass\n", timeout_sec=1)
    assert out["status"] == "timeout"


def test_blocks_operator_attrgetter_dunder_escape():
    # operator.attrgetter turns a string into attribute access, bypassing the AST dunder check
    code = "import operator\ndef main():\n    return operator.attrgetter('__globals__')(main)\n"
    assert cap.run_pure_gene(code)["status"] == "rejected"


def test_blocks_operator_rce_chain():
    # the full escape: string-attr → real __globals__ → real __builtins__ → __import__ → os
    code = (
        "import operator, json\n"
        "def main():\n"
        "    g = operator.attrgetter('__globals__')(json.dumps)\n"
        "    return operator.attrgetter('get')(g['__builtins__'])('__import__')('os').getuid()\n"
    )
    assert cap.run_pure_gene(code)["status"] == "rejected"


# --- manifest parsing ----------------------------------------------------------------------

def test_manifest_parsing_pure_with_grants():
    header = (
        "# life_id: PGN@L1-G3-CODE-REVIEWER\n"
        "# creator: Audrey\n"
        "# purity: pure\n"
        "# grants: [net:github.com, fs:read]\n"
    )
    m = cap.parse_capability_manifest(header)
    assert m["purity"] == "pure"
    assert m["creator"] == "Audrey"
    assert "net:github.com" in m["grants"] and "fs:read" in m["grants"]


def test_manifest_defaults_to_effectful():
    m = cap.parse_capability_manifest("# life_id: PGN@L1-G1-X\n")
    assert m["purity"] == "effectful" and m["grants"] == []
