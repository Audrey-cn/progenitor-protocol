"""L4 evolution — per-gene reputation, lineage, rollback, and the adoption feedback loop.

Proves the re-review bar (docs/AKASHIC_LAYERED_ARCHITECTURE.md §7 #4): a gene's score changes from
real usage, produces a lineage entry, and a regression triggers a rollback.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hatchery"))
import evolution  # noqa: E402
import adoption  # noqa: E402

V1 = "a" * 64
V2 = "b" * 64
V3 = "c" * 64


def test_score_moves_from_real_usage_and_records_lineage():
    led = evolution.GeneLedger()
    led.register_version("code-reviewer", V1)
    led.record_outcome(V1, success=True)
    led.record_outcome(V1, success=True)
    rec = led.reputation_of(V1)
    assert rec["uses"] == 2 and rec["successes"] == 2
    assert rec["score"] == 2.0
    assert led.health(V1) == 1.0
    # lineage captured each event, in order, without wall-clock
    assert [e["success"] for e in rec["lineage"]] == [True, True]
    assert [e["seq"] for e in rec["lineage"]] == [1, 2]


def test_consecutive_failures_retire_and_roll_back_to_prior_version():
    led = evolution.GeneLedger(retire_after_consecutive_failures=3)
    led.register_version("code-reviewer", V1)
    led.record_outcome(V1, success=True)              # v1 proven good
    led.register_version("code-reviewer", V2)         # adopt v2 as current
    assert led.current("code-reviewer") == V2

    led.record_outcome(V2, success=False)
    led.record_outcome(V2, success=False)
    result = led.record_outcome(V2, success=False)    # third consecutive failure → retire

    assert result["retired"] is True
    assert result["rollback_to"] == V1                # ref rolled back to last known-good
    assert led.current("code-reviewer") == V1
    assert led.reputation_of(V2)["status"] == "retired"


def test_score_floor_also_retires():
    led = evolution.GeneLedger(retire_floor=-3.0)
    led.register_version("flaky", V1)
    # max 2 consecutive failures (< default 3) so only the score floor can retire it
    for success in (False, False, True, False, False):
        res = led.record_outcome(V1, success=success)
    assert led.reputation_of(V1)["score"] <= -3.0
    assert led.reputation_of(V1)["consecutive_failures"] < 3
    assert res["retired"] is True


def test_rollback_skips_already_retired_versions():
    led = evolution.GeneLedger(retire_after_consecutive_failures=1)
    led.register_version("svc", V1)
    led.register_version("svc", V2)
    led.register_version("svc", V3)
    # retire v3 → rolls back to v2
    led.record_outcome(V3, success=False)
    assert led.current("svc") == V2
    # retire v2 → must skip v3 (retired) and land on v1
    led.record_outcome(V2, success=False)
    assert led.current("svc") == V1


def test_no_prior_version_rolls_back_to_none():
    led = evolution.GeneLedger(retire_after_consecutive_failures=1)
    led.register_version("solo", V1)
    result = led.record_outcome(V1, success=False)
    assert result["retired"] is True
    assert result["rollback_to"] is None
    assert led.current("solo") is None


def test_readopting_retired_version_revives_it():
    led = evolution.GeneLedger(retire_after_consecutive_failures=1)
    led.register_version("svc", V1)
    led.record_outcome(V1, success=False)             # retire v1
    assert led.reputation_of(V1)["status"] == "retired"
    led.register_version("svc", V1)                   # host deliberately re-adopts it
    assert led.reputation_of(V1)["status"] == "active"
    assert led.current("svc") == V1


def test_persistence_round_trip():
    led = evolution.GeneLedger()
    led.register_version("cap", V1)
    led.record_outcome(V1, success=True, note="ok")
    restored = evolution.GeneLedger.from_dict(led.to_dict())
    assert restored.reputation_of(V1)["score"] == 1.0
    assert restored.current("cap") == V1
    assert restored._seq == led._seq


def test_closed_loop_retired_gene_is_rejected_by_adoption():
    """The L4 → pillar-C loop: a gene retired by evolution is refused on its next adoption."""
    led = evolution.GeneLedger(retire_after_consecutive_failures=2)
    led.register_version("bad-gene", V1)
    led.record_outcome(V1, success=False)
    led.record_outcome(V1, success=False)             # retired
    assert led.reputation_signal("bad-gene") == "flagged"

    proposal = {"capability": "bad-gene", "trust_state": "creator-signed:Audrey",
                "purity": "pure", "hash_verified": True}
    decision = adoption.decide(proposal, reputation=led.reputation_signal("bad-gene"))
    assert decision["recommend"] == "reject"

    # a healthy capability yields no signal → adoption proceeds normally
    led.register_version("good-gene", V2)
    led.record_outcome(V2, success=True)
    assert led.reputation_signal("good-gene") is None
