# L4 Evolution — design (turning the label into a mechanism)

Implements layer **L4** from [AKASHIC_LAYERED_ARCHITECTURE.md](AKASHIC_LAYERED_ARCHITECTURE.md) §6.
Today "evolution" is an honest label: `EvolutionTracker.phase` is a usage counter on the *engine*,
and registry gene scores seed at 0 and never move ([VISION.md](VISION.md) marks this deferred). L4
makes it a real mechanism **per gene**, without claiming code self-modification or ML.

## What "real" means here (the bar from the re-review checklist)

> A gene's score changes from real usage, produces a lineage entry, and a regression triggers a
> rollback — with a test that proves it.

## The model — reputation + lineage as a Git-style ref

This reuses the **"Akashic is Git, not Syncthing"** insight:

- A **gene** is an immutable, content-addressed object (`content_sha256`). Its *reputation* is a
  property of that exact bytes — it never mutates, so its score is unambiguous.
- A **capability name → current hash** is a mutable **ref**. Its *lineage* is the ordered history
  of versions the host adopted for that capability (like a git reflog).
- **Rollback** = move the ref back to a prior immutable gene. No merge, no conflict — just repoint.

```
capability "code-reviewer"
   lineage:  [v1=ab12…, v2=cd34…, v3=ef56…]   (ref history)
   current:  ef56…  ── regresses ──▶  retire ef56…, roll ref back to cd34…
              │
              └─ each version (hash) carries its own reputation record from REAL outcomes
```

## Component: `hatchery/evolution.py` — `GeneLedger`

Pure, stdlib-only, `to_dict`/`from_dict` persistence (matches `capability.py` / `adoption.py` /
`transport.py` leaf-module style). Two structures:

- **per-gene record** keyed by `content_sha256`: `uses, successes, failures, score,
  consecutive_failures, status (active|retired), lineage[]`. `score` is a transparent net signal
  (`+weight` on success, `−weight` on failure) — no hidden ML.
- **per-capability ref**: `history[] (hashes in adoption order), current, retired[]`.

API:

| method | purpose |
|---|---|
| `register_version(capability, content_sha256)` | a new adopted version → append to ref history, set current |
| `record_outcome(content_sha256, success, weight=1.0, note="")` | real usage signal → update score + append a lineage event; auto-retire on regression |
| `rollback(capability)` | repoint the ref to the last known-good prior version; retire the current |
| `flagged()` | capabilities whose current version is retired → fed straight into `adoption.decide()`'s reputation gate |
| `health(content_sha256)` / `reputation_of(...)` | read a gene's standing |

**Retirement (regression) rule** — explicit and testable, no magic:
`consecutive_failures >= retire_after_consecutive_failures (default 3)` **or**
`score <= retire_floor (default −3)` → status becomes `retired` and `record_outcome` returns a
`rollback_to` suggestion (the prior active version, or None if none exists).

## The closed loop (why this ties the whole architecture together)

```
express_gene → outcome (success/failure)
            → ledger.record_outcome(hash)        # L4: score moves on REAL usage
            → regression → retire + rollback ref  # L4: lineage + rollback
            → ledger.flagged()                    # feeds…
            → adoption.decide(reputation=flagged) # …the EXISTING pillar-C gate → rejects the bad gene
```

`adoption.decide()` already rejects a capability that appears in its `reputation` argument
("capability is flagged in the reputation log"). L4 is what finally *populates* that argument from
evidence instead of leaving it empty. So L4 doesn't bolt on a new subsystem — it closes the loop
the other three pillars left open.

## Scope of this iteration (honest boundaries)

- ✅ per-gene reputation from real outcomes, per-capability lineage, regression→rollback, the
  adoption feedback loop, full unit tests.
- ✅ one real wire-in: `Phagocyte` records an outcome after `express_gene`, guarded/opt-in so
  existing flows are untouched when no ledger is attached.
- 🚧 *not* in scope: distributed reputation (peers exchanging signed scores), decay-over-time,
  Sybil-resistant aggregation. These are L4×L5 federation work, noted for the next pass.
