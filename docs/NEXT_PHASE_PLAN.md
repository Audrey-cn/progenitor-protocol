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

4. 🔶 Rejection log review in daily scan — partially done: `daily_scan.yml` publishes the
   audit summary and rejection/audit logs as artifacts. Still open: top-rejection-reasons
   analytics in the step summary.

5. ✅ Trust-state field in index — entries carry `trust_state` (e.g. `registry_verified`);
   per-creator signing upgrades it via the Gatekeeper trust flow.

6. ✅ README layer naming aligned — README/README_CN now match gatekeeper semantics
   (L1 lineage verify, L2 content-address check) and document L6 capability honesty.

### Remaining (restart backlog)

- WAN federation live test (IPFS pin/relay + transport-hint ladder on the real network).
- Windows `<3.12` fallback honesty: `TelomereGuard`/`run_pure_gene` time caps are soft via
  sys.monitoring (3.12+) and absent before that; tests skip where they would hang.
- First external gene contribution to prove the open model.

## Suggested Execution Order

1. Hash backfill and migration report.
2. Enable strict L2 in CI.
3. Decide and apply strict L4 policy.
4. Add rejection analytics to daily scan.
5. Add trust-state schema in index.
6. Final doc wording alignment pass.

## Acceptance Commands

```powershell
cd D:\trae\progenitor-registry
python .github\workflows\gatekeeper.py --scan-only
$env:GATEKEEPER_STRICT_L2='1'; python .github\workflows\gatekeeper.py --scan-only; Remove-Item Env:GATEKEEPER_STRICT_L2
```

```powershell
cd D:\trae\Git
python scripts\contract_check.py
python scripts\boundary_check.py
python scripts\encoding_check.py
python scripts\dependency_check.py
python -m pytest tests -q
```
