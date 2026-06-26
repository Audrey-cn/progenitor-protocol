"""Cross-peer ref reconciliation (docs/AKASHIC_LAYERED_ARCHITECTURE.md re-review #1).

The pointer-divergence that immutability does NOT remove, resolved by an explicit policy:
trusted + non-retired only, ranked by reputation then lineage; genuine ties go to the host.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hatchery"))
import federation as fed  # noqa: E402
import evolution  # noqa: E402

X = "a" * 64
Y = "b" * 64
Z = "c" * 64


def _cand(h, *, trust="creator-signed:Audrey", rep=0.0, retired=False, depth=0):
    return {"content_sha256": h, "capability": "cap", "trust_state": trust,
            "reputation": rep, "retired": retired, "lineage_depth": depth}


def test_higher_reputation_wins():
    out = fed.reconcile_refs([_cand(X, rep=1.0), _cand(Y, rep=5.0)])
    assert out["status"] == "resolved" and out["winner"] == Y


def test_retired_version_never_wins():
    # Y has the higher reputation but is retired → the eligible X wins
    out = fed.reconcile_refs([_cand(X, rep=1.0), _cand(Y, rep=9.0, retired=True)])
    assert out["status"] == "resolved" and out["winner"] == X


def test_untrusted_version_excluded():
    out = fed.reconcile_refs([_cand(X, trust="candidate", rep=9.0), _cand(Y, trust="tofu_trusted", rep=1.0)])
    assert out["winner"] == Y


def test_no_eligible_candidate():
    out = fed.reconcile_refs([_cand(X, trust="unknown", rep=9.0), _cand(Y, retired=True, rep=9.0)])
    assert out["status"] == "no_candidate" and out["winner"] is None


def test_lineage_breaks_reputation_tie():
    out = fed.reconcile_refs([_cand(X, rep=3.0, depth=2), _cand(Y, rep=3.0, depth=5)])
    assert out["status"] == "resolved" and out["winner"] == Y


def test_genuine_divergence_goes_to_host():
    # equal reputation AND equal lineage on distinct hashes → not silently resolved
    out = fed.reconcile_refs([_cand(X, rep=3.0, depth=2), _cand(Y, rep=3.0, depth=2)])
    assert out["status"] == "diverged" and out["winner"] is None
    assert set(out["candidates"]) == {X, Y}


def test_creator_signed_prefix_is_trusted():
    out = fed.reconcile_refs([_cand(X, trust="creator-signed:SomeoneElse", rep=2.0)])
    assert out["status"] == "resolved" and out["winner"] == X


def test_candidate_from_ledger_integrates_l4_state():
    led = evolution.GeneLedger(retire_after_consecutive_failures=2)
    led.register_version("cap", X)
    led.record_outcome(X, success=True)
    led.record_outcome(X, success=True)        # X: score 2, healthy
    led.register_version("cap", Y)
    led.record_outcome(Y, success=False)
    led.record_outcome(Y, success=False)       # Y: retired

    cx = fed.candidate_from_ledger(led, X, trust_state="creator-signed:Audrey")
    cy = fed.candidate_from_ledger(led, Y, trust_state="creator-signed:Audrey")
    assert cx["reputation"] == 2.0 and cx["retired"] is False and cx["lineage_depth"] == 2
    assert cy["retired"] is True
    # reconciliation picks the healthy, non-retired X over the retired Y
    assert fed.reconcile_refs([cx, cy])["winner"] == X


# --- wire exchange: reconcile across peer manifests --------------------------------------------

def _manifest(node_id, genes):
    return {"node": {"node_id": node_id}, "genes": genes}


def _g(h, *, rep=0.0, depth=0, retired=False, cap="cap"):
    return {"capability": cap, "content_sha256": h, "reputation": rep, "lineage_depth": depth, "retired": retired}


def test_reconcile_peer_manifests_picks_higher_reputation_among_trusted():
    manifests = [_manifest("peerA", [_g(X, rep=1.0)]), _manifest("peerB", [_g(Y, rep=4.0)])]
    out = fed.reconcile_peer_manifests(manifests, peer_trust={"peerA": "tofu_trusted", "peerB": "tofu_trusted"})
    assert out["cap"]["status"] == "resolved" and out["cap"]["winner"] == Y


def test_reconcile_ignores_untrusted_peer_self_claim():
    # peerA is NOT in our trust map → its high-reputation version is excluded; trusted peerB wins
    manifests = [_manifest("peerA", [_g(X, rep=9.0)]), _manifest("peerB", [_g(Y, rep=1.0)])]
    out = fed.reconcile_peer_manifests(manifests, peer_trust={"peerB": "tofu_trusted"})
    assert out["cap"]["winner"] == Y


def test_reconcile_excludes_peer_advertised_retired():
    manifests = [_manifest("peerA", [_g(X, rep=9.0, retired=True)]), _manifest("peerB", [_g(Y, rep=1.0)])]
    out = fed.reconcile_peer_manifests(manifests, peer_trust={"peerA": "tofu_trusted", "peerB": "tofu_trusted"})
    assert out["cap"]["winner"] == Y


def test_reconcile_folds_in_local_ledger_evidence():
    led = evolution.GeneLedger()
    led.register_version("cap", Z)
    for _ in range(6):
        led.record_outcome(Z, success=True)  # strong local evidence for Z
    manifests = [_manifest("peerA", [_g(X, rep=2.0)])]
    out = fed.reconcile_peer_manifests(manifests, peer_trust={"peerA": "tofu_trusted"}, local_ledger=led)
    assert out["cap"]["winner"] == Z  # our first-hand 'local' evidence outranks the peer's
