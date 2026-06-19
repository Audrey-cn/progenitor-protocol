# Changelog

Release record for Progenitor Protocol. Dates are authoritative. The engine's internal
`protocol_version` (currently **2.6**, in `hatchery/metadata.yaml`) is a separate schema
number used for gene-compatibility migrations — not a product release version.

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
