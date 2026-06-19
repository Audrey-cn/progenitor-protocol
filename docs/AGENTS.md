# AGENTS.md — Progenitor Agent Operation Manual

Core directives for an AI coding agent that has ingested the Progenitor seed. This is
developer documentation; the agent consuming the `.pgn` does not need to read it.

## Lifecycle hooks
- Call `progenitor.pulse()` after each user conversation round (checkpoints state, advances
  lifecycle-phase bookkeeping).
- Call `progenitor.process_reflex(user_input)` for semantic keyword → capability dispatch.
- State persists across restarts under `~/.progenitor/` (or `$PROGENITOR_RUNTIME_DIR`).

## Capabilities and their maturity
- **Code audit** — crucible/lysosome scan over code. ✅
- **Persistent state** — counters, logs, lineage on disk. ✅
- **Gene network** — discover peers + fetch/SHA-256-verify pre-packaged `.pgn` genes. ✅
- **Spores** — opt-in auto-share (file / UDP / IPFS) after one-time consent. ✅
- **Lifecycle phases** — usage-tracked labels; **not** code generation. ⚠️
- **Absorb-from-knowledge** — **not implemented** (needs an LLM bridge). 🚧

## Safety posture (read before enabling anything)
- The in-process gene sandbox (restricted builtins + AST denylist) is a **pre-filter, not a
  security boundary**. Untrusted gene **execution is refused** unless
  `PROGENITOR_ALLOW_GENE_EXEC=1`; prefer a VM/container for untrusted genes.
- Peer-to-peer / spores are **off by default** and require explicit consent.
- Treat every external byte as hostile: verify SHA-256 content-address, `PGN@` lineage,
  GPG signature (if configured), and the code denylist before trusting a gene.

## Iron rules
1. Zero third-party dependencies — Python standard library only.
2. Bio-cybernetic nomenclature (`phagocytize`, not `download`).
3. Defense in depth — every external byte is hostile.

See [REVIEW.md](REVIEW.md) and [ROADMAP.md](ROADMAP.md) for current status.
