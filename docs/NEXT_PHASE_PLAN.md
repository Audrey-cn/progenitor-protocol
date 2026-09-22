# Next-Phase Plan: Open Authorship + Verified Execution

This plan captures the remaining collection points and turns them into an execution backlog for the Akashic Stargate review model.

## Scope

- Keep contributor model open for humans and AI agents.
- Strengthen verification and containment instead of identity-based gating.
- Make migration safe for existing historical genes.

## What We Collected

1. Registry Gatekeeper accepted open creators, but lacked explicit L2 content-address enforcement in its main loop.
2. Daily scan invoked `--scan-only`, but Gatekeeper had no explicit scan-only branch.
3. Quality gate (L4) was warning-only; no strict-mode toggle existed.
4. Registry had no structured rejection log for failed checks.
5. Historical `genes/` entries include filename/hash mismatches, so hard-enforcing L2 immediately would break existing data.

## What We Implemented In This Iteration

1. Added explicit L2 content-address validator in Gatekeeper main flow.
2. Added `--scan-only` parser and branch to avoid writes in scan-only mode.
3. Added strictness toggle for L2:
   - `GATEKEEPER_STRICT_L2=0` (default): warning mode for migration.
   - `GATEKEEPER_STRICT_L2=1`: blocking mode.
4. Added strictness toggle for L4:
   - `GATEKEEPER_STRICT_L4=0` (default): warning mode.
   - `GATEKEEPER_STRICT_L4=1`: blocking mode.
5. Added structured rejection logs to `.gatekeeper_rejections.jsonl`.

## New To-do List

Status audit 2026-09-22 (Windows portability + restart pass):

1. ✅ Backfill historical gene hash alignment — DONE.
   The hash deltas observed on Windows were checkout line-ending corruption, not real
   mismatches; fixed by `.gitattributes` (content-addressed files are `-text`, byte-exact)
   plus byte-exact LF writes in gatekeeper/tools/tests. `gatekeeper.py --scan-only` is clean
   under strict L2.

2. ✅ Strict L2 is on — `gatekeeper.py` defaults `GATEKEEPER_STRICT_L2=1`.

3. ✅ L4 strictness policy decided — strict-by-default (`GATEKEEPER_STRICT_L4=1` in code);
   `daily_scan.yml` keeps a per-run strict override via workflow_dispatch inputs.

4. ✅ Rejection log review in daily scan — done: `daily_scan.yml` publishes the audit tail,
   rejection/audit logs as artifacts, AND `tools/rejection_report.py` analytics in the step
   summary (per-layer failure counts, top normalized failure reasons, recent rejections).

5. ✅ Trust-state field in index — entries carry `trust_state` (e.g. `registry_verified`);
   per-creator signing upgrades it via the Gatekeeper trust flow.

6. ✅ README layer naming aligned — README/README_CN now match gatekeeper semantics
   (L1 lineage verify, L2 content-address check) and document L6 capability honesty.

7. ✅ Windows portability pass (2026-09-22) — `.gitattributes` line-ending governance +
   byte-exact LF writes (protocol & registry), real off-Unix wall-clock caps via
   sys.monitoring in `run_pure_gene`/`TelomereGuard` (settrace legacy fallback; tests skip
   where no mechanism exists), byte-exact `.pgn` seed build, SECURITY.md signed-index truth.
   Protocol 184 / registry 45 tests green on Windows.

### Remaining (restart backlog)

Refined 2026-09-22. Dependency order: R1 → R2 → R3 are sequential (network evidence →
external adoption → release); R4 and R5 are independent and may proceed in parallel.

#### R1 — WAN federation live test (the big one; network evidence is the blocker)

The transport-hint ladder and self-certifying identity landed offline-tested. What is
missing is evidence on a real network, split into three runnable steps:

- **R1.1 IPFS path round-trip**
  - Action: pin one registry gene via `tools/ipfs_upload.py` (decide: local IPFS node vs
    public pinning service), then fetch it back through the engine's stargate transport
    from a second machine on a different network.
  - Exit criteria: fetched bytes hash-verify against `content_sha256`; the index
    signature verifies on the fetching machine.

- **R1.2 Transport-ladder failover on the real network**
  - Action: resolve one gene with all three hint classes active
    (`registry_path` → `github_raw` → `ipfs`), blocking one path at a time (firewall or
    offline simulation).
  - Exit criteria: the ladder skips the dead path and lands content-verified bytes from
    the next hint; the attempt sequence is logged.

- **R1.3 Cross-network peer exchange**
  - Action: UDP discovery is LAN-broadcast only. Add explicit peer hints
    (`--peer host:port` or env) if still missing, then exchange one signed gene between
    two agents on different networks.
  - Exit criteria: the peer manifest signature verifies against the local keyring; the
    trust/reputation upgrade is visible in the next trust report.

#### R2 — First external gene contribution (proves the open model)

- Action: write a contributor quickstart (`gene_scaffold.py` → `sign_gene.py` → PR) as
  `CONTRIBUTING.md`; verify the scaffold end-to-end on Windows (LF-exact writes landed)
  and on Linux CI; announce and mentor one external PR.
- Exit criteria: one merged gene authored by an external creator, passing L0–L6 with a
  per-creator signature, and its `trust_state` surfaced by `tools/trust_report.py`.

#### R3 — First tagged release (credibility + installability)

- Action: reconcile version claims (registry README says "v2.18", engine
  `protocol_version` is 2.6 — pick one scheme and document it in `CHANGELOG.md`); tag;
  publish a GitHub Release with the rebuilt `INGEST_ME_TO_EVOLVE_pgn-core.pgn` seed and
  its SHA-256.
- Exit criteria: the `curl | python3` quick start works against the release asset from a
  clean machine, and the release check passes.

#### R4 — OS-level sandbox hardening (long-term; pillar B)

- Action: the AST allowlist stays the pre-filter; evaluate seccomp/landlock/namespaces or
  wasm for effectful genes, out-of-process first (subprocess + resource caps exist).
- Exit criteria: an untrusted effectful gene runs with no ambient authority under an
  OS-enforced profile, demonstrated by a test.

#### R5 — LLM bridge reference implementation (optional)

- Action: wire `Phagocyte.register_llm_bridge` to a host-agent callable as a documented
  example without adding any engine dependency.
- Exit criteria: "absorb capability from raw knowledge" goes from honest
  `not_implemented` to an honest, host-provided reference path in `examples/`.

## Suggested Execution Order

Governance to-dos 1–7 above are all closed. The restart order:

1. **R1** WAN federation evidence (R1.1 → R1.2 → R1.3; R1.3's explicit peer hints are the
   only expected code change before testing).
2. **R2** external contribution — can start in parallel with R1 (onboarding docs have no
   network dependency).
3. **R3** tagged release — after R1, so the release ships network-tested claims.
4. **R4 / R5** — continuous, non-blocking.

## Acceptance Commands

Repo-relative (portable; verified on Windows + Linux CI, 2026-09-22):

```powershell
# Registry (gene pool) — from the registry repo root
python .github\workflows\gatekeeper.py --scan-only
$env:GATEKEEPER_STRICT_L2='1'; python .github\workflows\gatekeeper.py --scan-only; Remove-Item Env:GATEKEEPER_STRICT_L2
python tools\trust_report.py
python -m pytest tests/ -q
```

```powershell
# Protocol (engine) — from the protocol repo root
python -m pytest tests/ -q
python tools\contract_check.py
python hatchery\incubator.py   # rebuilds + pipe-bootstrap-validates the seed
```
