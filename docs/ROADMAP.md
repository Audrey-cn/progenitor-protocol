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

**✅ FIXED (2026-06-20) — the self-bootstrap install now works**
- The seed activates via `curl | python3`, `python3 seed.pgn`, and a terminal. The executable
  bootstrap now extracts `[PRIMORDIAL_PAYLOAD]` from the seed's own embedded `_` string (not
  stdin), and the incubator **inlines** the sibling modules (`stargate_transport` /
  `stargate_identity`) into the payload so the engine is self-contained on a neutral path.
  `validate_pipe_bootstrap` now asserts real activation. Verified: pipe + file (tty) both
  activate from `/tmp` with no source files on `sys.path`.

**P0 — credibility & safety (before any promotion)**
1. ✅ Closed the network/validation mediums: fetch **size caps** (F004), **content-address
   verified before landing** (F005), index moved out of **cwd** to the runtime dir (F006).
   Also made the remote audit scan code, and fixed two latent land-path crashers
   (`LYSOSOME_CAPACITY` / `uuid` undefined).
2. ⚠️ In-process exec story (F001): ✅ untrusted exec now refused by default (opt-in via
   `PROGENITOR_ALLOW_GENE_EXEC=1`), documented as a pre-filter; 🚧 a real OS sandbox
   (seccomp/landlock/namespaces) or fully out-of-process execution is still future work.
3. ✅ Security tests now exercise **real product code** (F007): `test_crucible_security` →
   `engine.Crucible`; `test_gatekeeper` + `test_gene_lifecycle` → real `gatekeeper.py`;
   `test_spore_propagation` → `engine.SporeDaemon`.
4. 🚧 Sign the registry index, so F005's hash check can't be subverted by a tampered index.

**P1 — make the headline real or drop it**
4. 🚧 Either build a real **LLM bridge** (text → vetted code) behind `self._llm_bridge`, or
   keep "absorb-from-knowledge" labeled not-implemented and stop implying it works (F003).
5. ⚠️ "Self-evolution": make it do something real, or rename to "lifecycle phases" everywhere.

**P2 — the distributed vision**
6. 🚧 Real peer handshake + trust store + the documented `peer-*` verbs (PEER_MESH plan).
7. ⏳ Split the 6,200-line `engine.py` into modules (`RUNTIME_AND_BUILD_PLAN.md`).
   ✅ **Step 1:** CI + `tools/release_check.sh` gate every change (exit-criterion #1).
   ✅ **Step 2:** `inline_sibling_modules` bundler in incubator registers source modules in
   `sys.modules` so the seed stays self-contained; first leaf extracted — `Parser` →
   `hatchery/manifest.py` (engine −148 lines), verified green + still activates from `/tmp`.
   🚧 **Remaining:** a few more clean leaves can move the same way (e.g. genesis/rosetta
   helpers, compass index helpers). The core classes (`Crucible` / `Progenitor` / `Phagocyte`
   / `ingest`) are mutually entangled and need real untangling first — do it leaf-by-leaf
   behind the green gate, not in one cut.
8. 🚧 Grow the registry beyond self-authored demo genes (prove the open model with ≥1 external contributor).

**P3 — hygiene** ✅ done
9. ✅ Version clarified: `CHANGELOG.md` is the release record; `protocol_version` (2.6) is the
   engine schema, distinct from the contract doc version. README "Defense in Depth" now
   describes the real runtime audit + the registry gatekeeper separately (was three conflated
   "L1–L5" schemes).
10. ✅ Added `CHANGELOG.md` and `docs/AGENTS.md`; fixed the broken `../AGENTS.md` README link;
    tagline corrected to "self-bootstrapping" (self-evolution is label-only).

## Done in the 2026-06-19 pass

Consolidated 3 repos → 2; fixed registry content-addressing; added LICENSE/topics; rewrote
READMEs for clarity + honest maturity. Security: `crucible_audit` code-scan + denylist
hardening (F001) + opt-in exec gate, signature fail-closed (F002), stub honesty (F003), fetch
size caps (F004), verify-before-land (F005), index out of cwd (F006), remote-audit code scan,
and all security tests rewritten onto real code (F007). Fixed a systemic latent-crash class:
**8 missing module-level imports** (`re`/`uuid`/`time`/`shutil`/`socket`/`subprocess`/`datetime`/
`urllib`) + undefined `LYSOSOME_CAPACITY` that crashed the spore/landing/sync paths on first
use. Stood up CI (protocol + registry) + `tools/release_check.sh` as the modularization safety
net (P2 step 1). Protocol 63 / registry 21 tests green (all real).
