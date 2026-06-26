"""L4 wire-in: Phagocyte.express_and_score feeds real expression outcomes into a GeneLedger.

Proves the full path on real product code: a gene that keeps failing to express is retired by
evolution and then flagged for adoption — exactly the closed loop in docs/L4_EVOLUTION_DESIGN.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hatchery"))
import engine  # noqa: E402
import evolution  # noqa: E402

GOOD_GENE = """# life_id: PGN@L1-G9-DOUBLER
# purity: pure
def main(x):
    return {"doubled": x * 2}
"""

BAD_GENE = """# purity: pure
import os
def main():
    return os.getcwd()
"""


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_no_ledger_is_plain_express_gene(tmp_path):
    p = engine.Phagocyte()  # ledger is None by default
    out = p.express_and_score(_write(tmp_path, "g.py", GOOD_GENE), {"x": 21})
    assert out["status"] == "proposed" and out["result"] == {"doubled": 42}
    assert "evolution" not in out  # nothing scored without a ledger


def test_good_expression_scores_a_success(tmp_path):
    p = engine.Phagocyte()
    p.ledger = evolution.GeneLedger()
    out = p.express_and_score(_write(tmp_path, "g.py", GOOD_GENE), {"x": 5}, capability="doubler")
    assert out["status"] == "proposed"
    assert out["evolution"]["status"] == "active"
    assert out["evolution"]["score"] == 1.0


def test_repeated_failed_expression_retires_and_flags(tmp_path):
    p = engine.Phagocyte()
    p.ledger = evolution.GeneLedger(retire_after_consecutive_failures=3)
    gene = _write(tmp_path, "bad.py", BAD_GENE)
    p.ledger.register_version("bad", _sha(gene))

    last = None
    for _ in range(3):
        last = p.express_and_score(gene, capability="bad")
        assert last["status"] == "rejected"  # AST allowlist refuses os
    assert last["evolution"]["retired"] is True
    # the loop closes: the retired gene is now flagged for adoption.decide
    assert p.ledger.reputation_signal("bad") == "flagged"


def _sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
