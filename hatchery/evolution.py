"""[evolution] L4 — per-gene reputation, lineage, and rollback (docs/L4_EVOLUTION_DESIGN.md).

Turns the lifecycle "phase" *label* into a real mechanism: a gene earns or loses standing from REAL
usage outcomes; every outcome is appended to that gene's lineage; a gene that regresses past an
explicit threshold is retired (apoptosis) and the capability's pointer rolls back to its last
known-good version.

This is the Git-style "ref over immutable objects" model (docs/AKASHIC_LAYERED_ARCHITECTURE.md §3):
a ``content_sha256`` is an immutable object whose reputation is unambiguous; a ``capability → current
hash`` is a mutable *ref* whose lineage is the version history; rollback simply repoints the ref to a
prior object — no merge, no conflict.

Honest boundaries: ``score`` is a transparent net signal (+weight on success, −weight on failure),
not ML and not code self-modification. Pure, stdlib-only, ``to_dict``/``from_dict`` persistence.
"""
from __future__ import annotations

DEFAULT_RETIRE_AFTER_CONSECUTIVE_FAILURES = 3
DEFAULT_RETIRE_FLOOR = -3.0


class GeneLedger:
    """Per-gene reputation + per-capability lineage with regression-triggered rollback."""

    def __init__(self, *, retire_after_consecutive_failures: int = DEFAULT_RETIRE_AFTER_CONSECUTIVE_FAILURES,
                 retire_floor: float = DEFAULT_RETIRE_FLOOR):
        self.retire_after = retire_after_consecutive_failures
        self.retire_floor = retire_floor
        self.genes: dict = {}          # content_sha256 -> reputation record
        self.capabilities: dict = {}   # capability name -> {history, current, retired}
        self._seq = 0                  # monotonic event counter (deterministic, no wall-clock)

    # --- gene records ----------------------------------------------------------------------

    def _gene(self, content_sha256: str, capability: str = "") -> dict:
        rec = self.genes.get(content_sha256)
        if rec is None:
            rec = {
                "capability": capability,
                "uses": 0, "successes": 0, "failures": 0,
                "score": 0.0, "consecutive_failures": 0,
                "status": "active", "lineage": [],
            }
            self.genes[content_sha256] = rec
        elif capability and not rec.get("capability"):
            rec["capability"] = capability
        return rec

    def register_version(self, capability: str, content_sha256: str) -> dict:
        """Record that ``content_sha256`` was adopted as a (new) version of ``capability``.

        Appends to the capability's ref history and makes it current. Idempotent: re-registering the
        current version is a no-op; re-adopting a previously-retired version revives it as current.
        """
        self._gene(content_sha256, capability)
        ref = self.capabilities.setdefault(capability, {"history": [], "current": None, "retired": []})
        if content_sha256 not in ref["history"]:
            ref["history"].append(content_sha256)
        if content_sha256 in ref["retired"]:
            ref["retired"].remove(content_sha256)
            self.genes[content_sha256]["status"] = "active"
            self.genes[content_sha256]["consecutive_failures"] = 0
        ref["current"] = content_sha256
        return ref

    # --- the real usage signal -------------------------------------------------------------

    def record_outcome(self, content_sha256: str, *, success: bool, weight: float = 1.0,
                       note: str = "", capability: str = "") -> dict:
        """Record one REAL usage outcome for a gene and update its standing.

        Returns ``{"status", "score", "retired": bool, "rollback_to": hash|None}``. When the outcome
        pushes the gene past the regression threshold it is retired and ``rollback_to`` carries the
        capability's prior known-good version (or None if there is none).
        """
        rec = self._gene(content_sha256, capability)
        self._seq += 1
        rec["uses"] += 1
        if success:
            rec["successes"] += 1
            rec["score"] += weight
            rec["consecutive_failures"] = 0
        else:
            rec["failures"] += 1
            rec["score"] -= weight
            rec["consecutive_failures"] += 1
        rec["lineage"].append({"seq": self._seq, "success": bool(success), "weight": weight, "note": note})

        retired = False
        rollback_to = None
        if rec["status"] == "active" and self._is_regressed(rec):
            rec["status"] = "retired"
            retired = True
            rollback_to = self._retire_and_rollback(rec.get("capability", capability), content_sha256)
        return {"status": rec["status"], "score": rec["score"], "retired": retired, "rollback_to": rollback_to}

    def _is_regressed(self, rec: dict) -> bool:
        return (rec["consecutive_failures"] >= self.retire_after) or (rec["score"] <= self.retire_floor)

    # --- ref rollback ----------------------------------------------------------------------

    def _retire_and_rollback(self, capability: str, content_sha256: str):
        if not capability or capability not in self.capabilities:
            return None
        ref = self.capabilities[capability]
        if content_sha256 not in ref["retired"]:
            ref["retired"].append(content_sha256)
        prior = self._last_known_good(ref)
        ref["current"] = prior
        return prior

    def _last_known_good(self, ref: dict):
        """Most recent version in history that is not retired — the rollback target."""
        for content_sha256 in reversed(ref["history"]):
            if content_sha256 in ref["retired"]:
                continue
            if self.genes.get(content_sha256, {}).get("status") == "retired":
                continue
            return content_sha256
        return None

    def rollback(self, capability: str):
        """Manually retire a capability's current version and repoint the ref to the prior good one.

        Returns the new current hash (or None if nothing good remains).
        """
        ref = self.capabilities.get(capability)
        if not ref or not ref.get("current"):
            return None
        current = ref["current"]
        self._gene(current, capability)["status"] = "retired"
        return self._retire_and_rollback(capability, current)

    # --- reads -----------------------------------------------------------------------------

    def current(self, capability: str):
        ref = self.capabilities.get(capability)
        return ref.get("current") if ref else None

    def health(self, content_sha256: str):
        """Success ratio in [0,1], or None if the gene has never been used."""
        rec = self.genes.get(content_sha256)
        if not rec or rec["uses"] == 0:
            return None
        return rec["successes"] / rec["uses"]

    def reputation_of(self, content_sha256: str) -> dict:
        rec = self.genes.get(content_sha256)
        return dict(rec) if rec else {}

    def flagged(self) -> dict:
        """Capabilities whose current version is retired (or have no good version left), with why."""
        out = {}
        for capability, ref in self.capabilities.items():
            current = ref.get("current")
            if current is None or self.genes.get(current, {}).get("status") == "retired":
                out[capability] = {"reason": "retired_by_evolution", "retired": list(ref.get("retired", []))}
        return out

    def reputation_signal(self, capability: str):
        """The exact signal ``adoption.decide(reputation=...)`` understands: ``"flagged"`` when this
        capability has been retired by evolution (so the pillar-C gate rejects it), else ``None``.
        This is the one-call bridge from L4 evidence into the existing adoption decision.
        """
        return "flagged" if capability in self.flagged() else None

    # --- persistence -----------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema_version": "akashic.gene-ledger/v1",
            "retire_after": self.retire_after,
            "retire_floor": self.retire_floor,
            "seq": self._seq,
            "genes": self.genes,
            "capabilities": self.capabilities,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GeneLedger":
        ledger = cls(
            retire_after_consecutive_failures=data.get("retire_after", DEFAULT_RETIRE_AFTER_CONSECUTIVE_FAILURES),
            retire_floor=data.get("retire_floor", DEFAULT_RETIRE_FLOOR),
        )
        ledger._seq = data.get("seq", 0)
        ledger.genes = data.get("genes", {}) or {}
        ledger.capabilities = data.get("capabilities", {}) or {}
        return ledger
