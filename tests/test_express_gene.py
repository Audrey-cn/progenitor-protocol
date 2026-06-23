"""Gene Contract v2 engine integration — Phagocyte.express_gene routes by declared purity."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hatchery"))
import engine  # noqa: E402


PURE_GENE = """# life_id: PGN@L1-G9-DOUBLER
# creator: Audrey
# purity: pure
# inputs: x: int
# outputs: doubled: int
def main(x):
    return {"doubled": x * 2}
"""

UNSAFE_PURE_GENE = """# purity: pure
import os
def main():
    return os.getcwd()
"""

EFFECTFUL_GENE = """# life_id: PGN@L1-G9-WRITER
# purity: effectful
# grants: [fs:write]
def main():
    return "side effect"
"""


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_pure_gene_runs_advisory_without_optin(tmp_path):
    p = engine.Phagocyte()
    out = p.express_gene(_write(tmp_path, "doubler.py", PURE_GENE), {"x": 21})
    assert out["status"] == "proposed"
    assert out["advisory"] is True
    assert out["purity"] == "pure"
    assert out["result"] == {"doubled": 42}


def test_unsafe_pure_gene_is_rejected(tmp_path):
    p = engine.Phagocyte()
    out = p.express_gene(_write(tmp_path, "evil.py", UNSAFE_PURE_GENE))
    assert out["status"] == "rejected"
    assert out["purity"] == "pure"


def test_effectful_gene_routes_to_sandbox_and_is_advisory(tmp_path):
    # effectful genes go through the process-isolated, opt-in-gated sandbox (gating itself is
    # covered by test_sandbox_gate); here we assert express_gene routes + annotates correctly.
    p = engine.Phagocyte()
    out = p.express_gene(_write(tmp_path, "writer.py", EFFECTFUL_GENE))
    assert out["purity"] == "effectful"
    assert out["advisory"] is True
    assert out["manifest"]["purity"] == "effectful"
    assert "fs:write" in out["manifest"]["grants"]


def test_effectful_refused_when_grant_not_consented(tmp_path):
    # gene declares fs:write; host consents to nothing → ungranted, never reaches the sandbox
    p = engine.Phagocyte()
    out = p.express_gene(_write(tmp_path, "writer.py", EFFECTFUL_GENE), grants=set())
    assert out["status"] == "ungranted"
    assert out["advisory"] is True
    assert "fs:write" in out["missing_grants"]


def test_effectful_proceeds_when_grant_consented(tmp_path):
    # host consents to fs:write → consent passes; routing proceeds (sandbox still OS-gated)
    p = engine.Phagocyte()
    out = p.express_gene(_write(tmp_path, "writer.py", EFFECTFUL_GENE), grants={"fs:write"})
    assert out["status"] != "ungranted"
    assert out["purity"] == "effectful" and out["advisory"] is True
    assert out["granted"] == ["fs:write"]


def test_missing_file_errors_cleanly(tmp_path):
    p = engine.Phagocyte()
    out = p.express_gene(str(tmp_path / "nope.py"))
    assert out["status"] == "error"
