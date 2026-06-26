"""[federation] L4×L5 — cross-peer ref reconciliation (docs/AKASHIC_LAYERED_ARCHITECTURE.md re-review #1).

Immutability removed conflicts at the *object* layer, but a ``capability → current hash`` *ref* that
multiple peers each advance re-introduces pointer divergence: peer A says "code-reviewer" is hash X,
peer B says it's hash Y. This resolves it with an explicit, signed, reputation-weighted policy over
the candidate versions — the federation analogue of a fast-forward check.

Policy, in order:
  1. **Eligibility** — drop versions that are *retired* (L4) or *untrusted* (L5: not creator-signed
     and not in the trusted set). A retired or unsigned version can never win.
  2. **Rank** — among the eligible, prefer higher *reputation* (L4 score); tie-break by deeper
     *lineage* (more recorded history / recency).
  3. **Decide** — a strict top → ``resolved``; a genuine tie between distinct hashes → ``diverged``
     (the host decides, we never pick silently); nothing eligible → ``no_candidate``.

Pure, stdlib-only. The host assembles candidates (from its GeneLedger + trust store + peer manifests)
and calls ``reconcile_refs``. Exchanging those candidates over the wire is future transport work.
"""
from __future__ import annotations

# Trust states accepted besides any "creator-signed:<owner>" (which is always trusted).
DEFAULT_TRUSTED_STATES = {"tofu_trusted"}


def _is_trusted(trust_state, trusted_states) -> bool:
    ts = trust_state or ""
    return ts.startswith("creator-signed:") or ts in trusted_states


def _rank(candidate) -> tuple:
    # higher reputation first, then deeper/more-recent lineage — a sortable tuple
    return (float(candidate.get("reputation", 0.0)), int(candidate.get("lineage_depth", 0)))


def reconcile_refs(candidates, *, trusted_states=None) -> dict:
    """Pick the winning version for a capability from divergent candidates.

    Each candidate: ``{content_sha256, capability?, trust_state, reputation, retired, lineage_depth}``.
    Returns ``{"status": "resolved"|"diverged"|"no_candidate", "winner": hash|None, "reason": str, ...}``.
    """
    trusted_states = DEFAULT_TRUSTED_STATES if trusted_states is None else set(trusted_states)

    # Dedup by hash, keeping the best-ranked metadata for each.
    by_hash = {}
    for c in candidates or []:
        h = c.get("content_sha256")
        if not h:
            continue
        if h not in by_hash or _rank(c) > _rank(by_hash[h]):
            by_hash[h] = c

    eligible = [c for c in by_hash.values()
                if not c.get("retired", False) and _is_trusted(c.get("trust_state"), trusted_states)]
    if not eligible:
        return {"status": "no_candidate", "winner": None,
                "reason": "no trusted, non-retired version available", "eligible": 0}

    ranked = sorted(eligible, key=_rank, reverse=True)
    top = ranked[0]
    top_rank = _rank(top)
    tied = [c["content_sha256"] for c in ranked
            if _rank(c) == top_rank and c["content_sha256"] != top["content_sha256"]]
    if tied:
        return {"status": "diverged", "winner": None,
                "reason": "multiple trusted versions tie on (reputation, lineage) — host must decide",
                "candidates": [top["content_sha256"], *tied]}

    return {"status": "resolved", "winner": top["content_sha256"],
            "reason": "highest-reputation trusted version",
            "rank": {"reputation": top_rank[0], "lineage_depth": top_rank[1]}}


def candidate_from_ledger(ledger, content_sha256: str, *, trust_state: str, capability: str = "") -> dict:
    """Build a reconciliation candidate from a GeneLedger record (L4) + a trust_state (L5)."""
    rec = ledger.reputation_of(content_sha256)
    return {
        "content_sha256": content_sha256,
        "capability": capability or rec.get("capability", ""),
        "trust_state": trust_state,
        "reputation": rec.get("score", 0.0),
        "retired": rec.get("status") == "retired",
        "lineage_depth": len(rec.get("lineage", [])),
    }


# Trust state given to our own first-hand ledger evidence (always counts).
LOCAL_TRUST_STATE = "local"


def reconcile_peer_manifests(manifests, *, peer_trust=None, local_ledger=None, trusted_states=None) -> dict:
    """Reconcile divergent capability refs advertised across peer manifests + our own ledger.

    ``manifests``: peer manifest dicts (each has ``node``/``node_id`` and ``genes[]`` carrying
    ``content_sha256`` + advertised ``reputation``/``lineage_depth``/``retired``).
    ``peer_trust``: ``{peer_node_id: trust_state}`` — **OUR** trust in each peer. A peer's *self*-
    advertised gene trust_state is ignored on purpose; an unknown peer defaults to ``candidate``
    (untrusted → its versions are excluded), so a stranger cannot inject a winner by claiming trust.
    ``local_ledger``: our GeneLedger — folds our first-hand evidence in as ``local`` (always trusted).

    Returns ``{capability: reconcile_refs(...) result}``.
    """
    peer_trust = peer_trust or {}
    ts = (DEFAULT_TRUSTED_STATES | {LOCAL_TRUST_STATE}) if trusted_states is None else set(trusted_states)

    by_cap = {}
    for manifest in manifests or []:
        node = manifest.get("node") or {}
        node_id = node.get("node_id") or manifest.get("node_id", "")
        trust_state = peer_trust.get(node_id, "candidate")  # our trust in the advertiser, not its claim
        for gene in manifest.get("genes", []):
            cap, h = gene.get("capability"), gene.get("content_sha256")
            if not cap or not h:
                continue
            by_cap.setdefault(cap, []).append({
                "content_sha256": h,
                "capability": cap,
                "trust_state": trust_state,
                "reputation": float(gene.get("reputation", 0.0)),
                "retired": bool(gene.get("retired", False)),
                "lineage_depth": int(gene.get("lineage_depth", 0)),
            })

    if local_ledger is not None:
        for cap, ref in local_ledger.capabilities.items():
            for h in ref.get("history", []):
                by_cap.setdefault(cap, []).append(
                    candidate_from_ledger(local_ledger, h, trust_state=LOCAL_TRUST_STATE, capability=cap))

    return {cap: reconcile_refs(cands, trusted_states=ts) for cap, cands in by_cap.items()}
