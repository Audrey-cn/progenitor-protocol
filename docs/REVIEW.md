# Progenitor — Engineering Review (2026-06-19)

Evidence-first review of `progenitor-protocol` + `progenitor-registry`. Every claim below
was checked against the source (file:line) and, for security items, reproduced. This file
is the honest baseline for the next development phase; see [ROADMAP.md](ROADMAP.md).

## 1. One-line assessment

A **solid sandbox-and-distribution skeleton** (real security screening, on-disk state,
real peer/spore transport) wearing the costume of a **self-evolving organism**. The
unglamorous half works; several headline claims were marketing or stubs and have now been
corrected in the READMEs.

## 2. Capability maturity (honest)

| Capability | Status | Note |
|---|---|---|
| Code audit (AST denylist + integrity/lineage/signature) | ✅ working | denylist is ~34 entries, not "200+"; hardened against escape gadgets this pass |
| Persistent cross-session state | ✅ working | zlib+sha256 JSON to `~/.progenitor/`; it's state, not "learning" |
| Peer/spore transport (UDP discovery, HTTP gateway, file spore, IPFS) | ✅ working | consent-gated |
| Lifecycle "phases" (mutation→adaptation→evolution) | ⚠️ label-only | a string set by a usage counter (`engine.py:1205`); does **not** mutate code |
| Absorb capability from raw text/knowledge | 🚧 not implemented | `_llm_bridge_translate_stub` (`engine.py:~2495`) returns canned self-passing code |

## 3. Test-coverage reality

92 tests pass, but ~half assert on logic **re-implemented inside the test files** or on
inert constants, not on shipped code:
- `test_crucible_security.py` (21) defines its own `crucible_*` and never imports `engine`.
- `test_gatekeeper.py` (24) never imports `gatekeeper.py` (different signatures).
- Real coverage touches only ~5 of `engine.py`'s 21 classes; `Progenitor`, `Parser`, and the
  `Crucible` class are untested. (The module-level `crucible_audit()` now has real tests.)

## 4. Security findings

Verified by reading + reproduction. Status reflects work done in this review pass.

| ID | Severity | Finding | Status |
|---|---|---|---|
| (prior) | high | `crucible_audit` NameError (missing `import re`); never scanned gene code | ✅ fixed |
| F001 | critical | AST denylist bypassable (`getattr`/`__subclasses__`/`__builtins__[...]`); in-process restricted-builtins is not a boundary | ⚠️ denylist hardened + tests; in-process exec remains defense-in-depth only |
| F002 | high | GPG verify failed **open** on exception even in strict mode (`engine.py:4406`) | ✅ fixed (fail-closed) + test |
| F003 | high | "Absorb from knowledge" faked success via a stub | ✅ honest `not_implemented` + README corrected |
| F004 | medium | No response size limit on network fetches (DoS) | ✅ fixed (8 MB cap in transport + land + index reads) |
| F005 | medium | Hash verified **after** landing and often skipped (`expected_sha256=None`) | ✅ fixed (verify sha256 == CID before landing) |
| F006 | medium | Unauthenticated remote index written to cwd controls the "expected" hash | ✅ partial (writes to runtime dir now; index still unsigned — P2) |
| F007 | medium | ~half of tests assert on re-implementations, not product code | ✅ partial (crucible + gatekeeper now hit real code; gene_lifecycle/spore remain) |
| F008 | low | `getattr`-by-name tool dispatch can reach private methods | ⏳ open |
| F009 | low | `TelomereGuard` enforces no memory cap on non-Unix | ⏳ open |
| — | low | `audit_gene_ast` misses dotted import aliases (`import os.path`) | ⏳ open (secondary scanner) |

> Note on F001: the lysosome denylist now blocks the common escape gadgets, but a denylist
> is defense-in-depth, not a security boundary. Untrusted gene execution should ultimately
> run under a real OS sandbox (seccomp/landlock/namespaces) or not in-process at all.

## 5. Direction gap

Documented as a **decentralized, signed, peer-to-peer capability mesh**; actually a
**single-author, GitHub-centered, 6,200-line monolithic script** with ~6 self-authored demo
genes. The peer mesh has only its lowest primitives (identity signing, candidate peer
store, beacon scaffolding); the documented CLI verbs (`peer-add/discover/handshake/resolve`)
don't exist; the `engine.py` modularization in `RUNTIME_AND_BUILD_PLAN.md` hasn't started.

Doc/code drift to clean up: incoherent version numbers (2.18 / 2.0 / 1.0.0 / 2.2 / 2.5 / 2.6),
three different meanings of "L1–L5", and README links to a non-existent `CHANGELOG.md` and
`../AGENTS.md`.

## 6. Fixed across this review's passes

- F001 denylist hardening (+3 tests), F002 fail-closed (+2 tests), F003 honesty.
- F004 fetch size caps, F005 content-address verified before landing, F006 index moved out
  of cwd into the runtime dir (+5 tests).
- **Remote audit now scans code:** `_crucible_remote` (the peer/IPFS download path) was
  lineage-only and never ran the lysosome; it now scans for denylisted calls and accepts the
  real `# life_id:` header format.
- **Two more latent crashers fixed in the gene-landing path:** `LYSOSOME_CAPACITY` was
  referenced but never defined, and `uuid`/`time` were not imported at module level — so
  `_local_write_before_ingest` / `_autophagy` `NameError`'d on *every* download (same class
  as the earlier `import re` bug; the landing path was simply never exercised).
- **F007 (partial): security tests rewritten onto real code.** `test_crucible_security.py`
  now exercises the real `engine.Crucible` (L1/L2/L4 — that class had zero coverage before);
  `test_gatekeeper.py` now imports and calls the real `gatekeeper.py` validators (it was
  never imported). ~16 fake/trivial re-implementation tests were removed — the suite count
  dropped (102→86) but the coverage is now genuine. (`test_gene_lifecycle`, `test_spore_propagation` still to do.)
- README/README_CN: real audit description, maturity column, corrected safety wording.
- Seed (`.pgn`) rebuilt as needed; **protocol 64 / registry 22 tests green (all real).**
