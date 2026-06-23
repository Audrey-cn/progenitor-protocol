# Changelog

Release record for Progenitor Protocol. Dates are authoritative. The engine's internal
`protocol_version` (currently **2.6**, in `hatchery/metadata.yaml`) is a separate schema
number used for gene-compatibility migrations — not a product release version.

## 2026-06-21 — P0 + P1: index signing & LLM bridge honesty

### P0: Registry index signing (F006)
- **Signed the registry index** to close F006 (unauthenticated remote index). The
  `.akashic_index.json.sig` envelope is now produced by `progenitor-registry/tools/sign_index.py`
  using the same RSA-SHA256 scheme as peer manifests (`stargate_identity`), committed
  alongside the index, and verified by the engine **before** the index is trusted.
- **Protocol side:** added `_fetch_and_verify_index_signature()` and
  `_should_verify_index_signature()` to `engine.py`; `_compass_resolve()` now fetches and
  verifies `.sig` after downloading the index, refusing in strict mode (default).
- **Tools side:** added `verify_index_signature()` and `load_registry_public_key()` to
  `stargate_resolver.py`; wired into `verify-index` and `health` CLI commands.
- **Config:** `PROGENITOR_INDEX_SIGNATURE_MODE` (default `strict`), `PROGENITOR_REGISTRY_PUBLIC_KEY`
  (env-var override), with a hard-coded default public key.
- **Registry:** public key published at `policy/registry_public_key.json`.
- **Tests:** 7 new signature-verification tests.

### P1: LLM bridge honesty (F003)
- **Removed dead stub code:** `_llm_bridge_translate_stub` and `_llm_bridge_repair_stub`
  that returned canned self-passing code and printed "Simulated Execution".
- **Added clean extension point:** `Phagocyte.register_llm_bridge(translate_fn, repair_fn=None)`
  so a host Agent can wire a real text→code translation callable.
- `phagocytize_and_evolve` now returns `not_implemented` by default (was already honest
  since the 6/19 pass; this round removed the dead code and added the registration API).
- **Tests:** 6 new LLM bridge tests. Protocol 76 tests green.

## 2026-06-20 — Self-bootstrap install fixed

- The headline install was a **no-op**: the executable bootstrap re-read already-consumed
  stdin and only ran under `not isatty()`, so `curl | python3` **and** `python3 seed.pgn`
  activated nothing (only direct `from engine import ingest; ingest(seed)` worked).
- **Fixed in `incubator.py`:** the executable bootstrap now reads `[PRIMORDIAL_PAYLOAD]` from
  the seed's own embedded `_` string, and the build **inlines** `stargate_transport` /
  `stargate_identity` into the payload (via `sys.modules` registration) so the engine is
  self-contained when exec'd on a neutral path. `validate_pipe_bootstrap` now asserts real
  activation instead of passing on the no-op. Verified across pipe + file (tty) modes.
- **Modularization step 1:** extracted the YAML `Parser` into `hatchery/manifest.py`; the
  incubator now inlines sibling source modules (`stargate_transport` / `stargate_identity` /
  `manifest`) into the payload via `sys.modules`, so the seed stays one self-contained file.

## 2026-06-19 — Consolidation & security hardening

### Repo / project
- Consolidated the Progenitor family from **3 repos to 2** (dissolved `progenitor-devkit`;
  its tooling + tests were absorbed into `progenitor-protocol` / `progenitor-registry`).
- Added MIT `LICENSE`, repository topics, and honest README maturity labelling.

### Security
- Fixed `crucible_audit` crash (missing `import re`) and made it scan gene code via the
  lysosome denylist.
- Hardened the denylist against `getattr` / `__subclasses__` / `__builtins__[...]` escape
  gadgets (F001).
- GPG signature verification now fails **closed** in strict mode (F002).
- Network fetches are size-capped (F004); downloaded gene content is hash-verified **before**
  landing (F005); the remote index is written to the runtime dir, not the cwd (F006).
- Untrusted gene **execution** is refused unless `PROGENITOR_ALLOW_GENE_EXEC=1` — the
  in-process denylist is a pre-filter, not a security boundary.

### Correctness
- Fixed a systemic latent-crash class: 8 stdlib modules were imported only locally inside
  methods, so module-level helpers (`_drop_spore_file`, `compass_sync_index`,
  `_local_write_before_ingest`, …) crashed on first call. Added module-level imports for
  `re`, `uuid`, `time`, `shutil`, `socket`, `subprocess`, `datetime`, `urllib`, and defined
  the previously-undefined `LYSOSOME_CAPACITY`.
- Re-addressed all registry genes to their true content hashes (content-addressing had been
  broken by an earlier migration).

### Honesty
- "Absorb capability from raw knowledge" now reports `not_implemented` instead of faking
  success (it needs an LLM bridge that does not ship); README marks it 🚧.
- "Self-evolution" relabelled as usage-tracked **lifecycle phases** — it does not rewrite code.

### Tests
- Rewrote the security/lifecycle tests to exercise **real product code** (`engine.Crucible`,
  `gatekeeper.py`, `engine.SporeDaemon`) instead of in-test re-implementations.
- protocol **63** + registry **21** tests green.

See [docs/REVIEW.md](docs/REVIEW.md) and [docs/ROADMAP.md](docs/ROADMAP.md) for the full
review and prioritized next steps.
