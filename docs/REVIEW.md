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
| F001 | critical | AST denylist bypassable (`getattr`/`__subclasses__`/`__builtins__[...]`); in-process restricted-builtins is not a boundary | ✅ denylist hardened + untrusted exec refused unless `PROGENITOR_ALLOW_GENE_EXEC=1` (+tests); real OS sandbox still future |
| F002 | high | GPG verify failed **open** on exception even in strict mode (`engine.py:4406`) | ✅ fixed (fail-closed) + test |
| F003 | high | "Absorb from knowledge" faked success via a stub | ✅ honest `not_implemented` + README corrected |
| F004 | medium | No response size limit on network fetches (DoS) | ✅ fixed (8 MB cap in transport + land + index reads) |
| F005 | medium | Hash verified **after** landing and often skipped (`expected_sha256=None`) | ✅ fixed (verify sha256 == CID before landing) |
| F006 | medium | Unauthenticated remote index written to cwd controls the "expected" hash | ✅ partial (writes to runtime dir now; index still unsigned — P2) |
| F007 | medium | ~half of tests assert on re-implementations, not product code | ✅ done (crucible, gatekeeper, gene-lifecycle, spore all exercise real code) |
| (new) | high | Module-level helper functions crashed on every call — stdlib modules imported only locally | ✅ fixed (8 missing module-level imports + undefined `LYSOSOME_CAPACITY`) |
| (new) | **critical** | **Self-bootstrap install is a no-op.** The executable top bootstrap only runs under `not sys.stdin.isatty()` and re-reads already-consumed stdin; the complete bootstrap (file/`__file__`/auto-discover) is embedded as inert documentation in the `_="""..."""` string. So `curl \| python3` **and** `python3 seed.pgn` activate nothing. Only `from engine import ingest; ingest(seed)` works (how tests + `validate_pgn` use it — which is why everything stayed green). `validate_pipe_bootstrap` passes on the no-op. | ✅ fixed (2026-06-20) — bootstrap reads the embedded payload + incubator inlines the stargate modules; pipe & file both activate from a neutral dir; pipe-bootstrap CI now asserts real activation |
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

Doc/code drift (✅ resolved 2026-06-19): version numbers clarified (`CHANGELOG.md` is the
release record; `protocol_version` 2.6 is the engine schema, distinct from the contract doc
version); README "Defense in Depth" now describes the runtime audit + registry gatekeeper
separately instead of three conflated "L1–L5" schemes; `CHANGELOG.md` and `docs/AGENTS.md`
added and the broken links fixed.

## 6. Fixed across this review's passes

- F001 denylist hardening (+3 tests), F002 fail-closed (+2 tests), F003 honesty.
- F004 fetch size caps, F005 content-address verified before landing, F006 index moved out
  of cwd into the runtime dir (+5 tests).
- **Remote audit now scans code:** `_crucible_remote` (the peer/IPFS download path) was
  lineage-only and never ran the lysosome; it now scans for denylisted calls and accepts the
  real `# life_id:` header format.
- **F007 (done): all four security/lifecycle test files now exercise real code.**
  `test_crucible_security` → real `engine.Crucible` (L1/L2/L4; that class had zero coverage);
  `test_gatekeeper` → real `gatekeeper.py` validators (was never imported);
  `test_gene_lifecycle` → real `gatekeeper.audit_gene` pipeline; `test_spore_propagation` →
  real `engine.SporeDaemon`. ~16 fake/trivial re-implementation tests removed.
- **F001 (gate): untrusted gene execution is refused by default.** `_sandbox_worker` returns
  `exec_disabled` unless `PROGENITOR_ALLOW_GENE_EXEC=1`; the in-process denylist is documented
  as a pre-filter, not a boundary. A real OS sandbox remains future work.
- **Systemic latent-crash bug class fixed.** The engine's module-level helper functions
  relied on stdlib modules imported only *locally inside methods*, so they `NameError`'d on
  *every* call. Found + fixed **8** missing module-level imports — `re`, `uuid`, `time`,
  `shutil`, `socket`, `subprocess`, `datetime`, `urllib` (plus the undefined `LYSOSOME_CAPACITY`).
  This means the advertised spore-drop, content-landing, autophagy, and index-sync paths were
  **never actually runnable** — they crashed on first use, undetected because untested. The
  F007 real-code tests surfaced them one by one.
- README/README_CN: real audit description, maturity column, corrected safety wording.
- Seed (`.pgn`) rebuilt as needed; **protocol 63 / registry 21 tests green (all real).**
