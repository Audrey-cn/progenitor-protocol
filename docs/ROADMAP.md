# Progenitor — Roadmap

Honest status + next steps, derived from the [2026-06-19 review](REVIEW.md). Tags:
✅ done · ⚠️ partial/label-only · 🚧 not started.

## Vision

A portable, zero-dependency capability layer you inject into any AI coding agent via one
self-extracting file — giving it a security-screened way to **fetch, verify, and run
reusable capability modules ("genes")**, persistent cross-session state, and (eventually) a
**decentralized, signed peer-to-peer** exchange for those modules. In plain terms: a
package-manager-plus-sandbox for AI-agent skills.

## Now (works today)

- ✅ Single-file `.pgn` self-bootstrap (`incubator.py` builds it from `hatchery/`)
- ✅ Security screening: integrity / lineage / GPG-signature + AST dangerous-call denylist
  (hardened; fail-closed signatures in strict mode)
- ✅ Subprocess isolation + `TelomereGuard` (time/mem caps on Unix)
- ✅ On-disk cross-session state (`CrystallizedPersistence`)
- ✅ Peer/spore transport: UDP discovery, HTTP gene gateway, file spore, IPFS publish (consent-gated)
- ✅ Registry: content-addressed genes + Gatekeeper CI (L0–L5)

## Next (prioritized)

**P0 — credibility & safety (before any promotion)**
1. 🚧 Close remaining security mediums: response **size caps** on all fetches (F004);
   **verify hash before landing/parsing**, require `expected_sha256` from the index (F005);
   stop writing the index to **cwd** and treat the unsigned index as untrusted (F006).
2. 🚧 Decide the in-process exec story: move untrusted gene execution under a real OS
   sandbox, or keep it out-of-process and document the denylist as a speed bump (F001).
3. 🚧 Point the "security" tests at **real product code** — import and exercise `Crucible`
   and `gatekeeper.py` instead of re-implementations (F007).

**P1 — make the headline real or drop it**
4. 🚧 Either build a real **LLM bridge** (text → vetted code) behind `self._llm_bridge`, or
   keep "absorb-from-knowledge" labeled not-implemented and stop implying it works (F003).
5. ⚠️ "Self-evolution": make it do something real, or rename to "lifecycle phases" everywhere.

**P2 — the distributed vision**
6. 🚧 Real peer handshake + trust store + the documented `peer-*` verbs (PEER_MESH plan).
7. 🚧 Split the 6,200-line `engine.py` into the modules in `RUNTIME_AND_BUILD_PLAN.md`.
8. 🚧 Grow the registry beyond self-authored demo genes (prove the open model with ≥1 external contributor).

**P3 — hygiene**
9. 🚧 Single source of truth for the version number; reconcile the three "L1–L5" models.
10. 🚧 Add `CHANGELOG.md` (or remove the README link); resolve the `../AGENTS.md` link.

## Done in the 2026-06-19 pass

Consolidated 3 repos → 2; fixed registry content-addressing; added LICENSE/topics; rewrote
READMEs for clarity + honest maturity; fixed `import re` crash, `crucible_audit` code-scan,
denylist bypass (F001), signature fail-open (F002), and stub honesty (F003).
