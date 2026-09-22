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

- **✅ R1.1 IPFS path round-trip — DONE 2026-09-22 (Kubo 0.34.1, local node via option A)**
  - Evidence: gene `5a702b24…` (hello-world-test) published+pinned — CID
    `bafkreic2oavsjmmzwionmexgeiobwwcfby52kbgifwzpqzxqk4uyygalkq` (raw-leaf CIDv1 = base32 of the
    content SHA-256). A second node (independent identity, mDNS off, public bootstraps only,
    128 swarm peers) resolved the provider via the **public DHT** (`routing findprovs`) and
    fetched the bytes over the network: SHA-256 byte-identical to the registered `content_sha256`.
  - Engine integration (`hatchery/transport.py`): ipfs-hint fetch verified; dead-gateway failover
    verified; wrong expected hash → `hash_mismatch` → `exhausted` (content-addressing red line).
  - Tooling (registry#4): `ipfs_upload.py`/`ipfs_pull.py` now stdlib-only (Kubo RPC v0; drops
    deprecated `ipfshttpclient`); index updates are attach-only + `--no-index` (rewrites need
    re-signing with the registry root key).
  - Known limitation: public gateways (ipfs.io/dweb.link/w3s.link) answer 403 and 4everland 504
    from this network region — DHT+relay transport is the verified path; gateway reachability from
    other regions still to be sampled (fold into R1.2).
  - Residual for R1.3: attaching `ipfs` transport hints to the live index requires re-signing
    with the registry root key (key ceremony is maintainer-held).

- **✅ R1.2 Transport-ladder failover on the real network — DONE 2026-09-22**
  - Method: live `Phagocyte.acquire_gene` runs against the real index entry (hello-world,
    sha `5a702b24…`) with per-scenario env — dead-proxy (127.0.0.1:9) as a genuine
    network-layer WAN block (`NO_PROXY` exempts the local daemon), `PROGENITOR_GATEWAY_ARRAY`
    override, empty `base_dir`, and a stopped IPFS daemon. Reproducible runner:
    `D:\项目\tools\r12_run.py`.
  - Evidence (attempts log per scenario):
    - S0 baseline (file present): lands `registry_path`, 1 attempt, `ok`.
    - S1 file blocked: `registry_path` unavailable → `github_raw` real fetch `ok`.
    - S2 file + WAN blocked, local daemon alive: → `github_raw` `error: URLError` →
      `ipfs` `ok` (content-verified via local gateway).
    - S3 all three blocked (daemon down): `exhausted` — honest failure, full attempt log
      (`unavailable` / `error: URLError` / `unavailable`), no fake success.
    - S4 recovery (daemon restarted): ipfs path lands again, bytes verified.
  - Exit criteria met: dead paths skipped, content-verified bytes land from the next hint,
    attempt sequence logged end-to-end.

- **✅ R1.3 Cross-network peer exchange — protocol chain DONE 2026-09-22 (no new engine code needed)**
  - Survey verdict: everything required already exists — `LocalGateway` binds all interfaces and
    serves `/hello` (self-certifying identity handshake), `/manifest` (signed
    `akashic.peer-manifest/v1` with per-gene transport hints + L4 reputation), `/gene/{name|hash}`;
    `federation.reconcile_peer_manifests` gates candidates by OUR trust in the peer; `peer`/
    `peer_hash` hints are plain HTTP through the existing ladder.
  - Live evidence (two independent agent processes, separate identities/keyrings, loopback):
    1. B verifies A's self-certifying identity via `/hello` (`verify_node_identity`).
    2. B verifies the signed manifest against the handshake public key — then TOFU-upgrades A into
       B's local keyring (`agent_b_keyring.json`).
    3. Federation: with A trusted → `resolved`, winner = `5a702b24…`; **negative test** — the same
       manifest from an untrusted peer → `no_candidate` (stranger-injection defense holds).
    4. `acquire_gene` over the manifest's `peer_hash` hint: 455 bytes, hash-verified.
    5. Voluntary adoption: `decide` honestly says **ask** (TOFU provenance not yet in the adoption
       trust set + effectful gene), host explicitly approves → content-addressed `adopted` cache.
  - Runner: `D:\项目\tools\agent_a.py` (provider, port 8620) + `agent_b.py` (verifier).
  - Residual (infra, not code): a true cross-machine run only needs the provider gateway to be
    reachable (port-forward/tunnel or same-LAN IP — the server already binds all interfaces);
    registry-side `trust_report` upgrade for creator-signed genes continues via the Gatekeeper PR
    flow (requires the maintainer-held key ceremony).

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

- Plan approved: **[R4_SANDBOX.md](R4_SANDBOX.md)** — threat model + options matrix + staged
  increments (Stage 1 Linux seccomp denylist in the sandbox preexec, CI-verifiable; Stage 2
  Landlock FS scoping + Windows Job Objects; Stage 3 namespaces best-effort).
- Action now: implement Stage 1 (`hatchery/sandbox_linux.py`) with the ubuntu-CI exit test.
- Exit criteria: an untrusted effectful gene attempting network/exec/write inside the sandbox
  is blocked by the kernel (EPERM), a benign pure gene is unaffected, both on CI.

#### ✅ R5 — LLM bridge reference implementation — DONE 2026-09-22

- `examples/llm_bridge_reference.py`: spec-mode bridge (JSON gene spec -> gene source,
  deterministic, offline) + `make_llm_bridge(llm_chat)` wrapper pattern for real hosts.
- End-to-end tests (`tests/test_llm_bridge_reference.py`): register bridge ->
  `phagocytize_and_evolve(raw)` -> lysosome pass -> sandbox verify self-check ->
  crystallization -> `evolution_complete`; repair-loop recovery; dangerous-spec rejection.
- "Absorb capability from raw knowledge" now has an honest, working reference path.

## Suggested Execution Order

Governance to-dos 1–7 above are all closed. The restart order:

1. ✅ **R1** WAN federation evidence — R1.1/R1.2/R1.3 all closed 2026-09-22 (IPFS round-trip,
   ladder failover, signed peer exchange). Remaining R1-adjacent: cross-machine leg is infra
   (port-forward/tunnel), and index ipfs-hint attachment awaits the key ceremony.
2. **R2** external contribution — unblocked; onboarding docs have no network dependency.
3. ✅ **R5.5 spore-consent revocation — DONE 2026-09-22**: `SporeDaemon.revoke_consent()`
   stops the UDP beacon, re-closes all channels, and is QUIET (revocation != denial: no
   reminder nagging); re-grant after revoke verified; revoked daemon refuses
   `auto_disseminate` (`consent_required`). Wired as `revoke_spore_consent` tool.
   Per-destination scoping remains open (follow-up).
3. **R3** tagged release — after R1, so the release ships network-tested claims.
4. **R4 / R5** — continuous, non-blocking.

## Linux 环境接手清单（切换系统环境时从此处续接）

> 2026-09-22 记录。以下任务因需要真实 seccomp/Linux 环境而挂起：GH Actions runner 的
> 安全 profile 拒绝嵌套 seccomp 安装——6 条指令的有效过滤器（字节级 hex 已验证正确）
> 经 prctl(22) 与 seccomp(2) 双路径均返回 EINVAL。本机 Windows 未装 WSL——
> `wsl --install` 即可在本机获得可用的 seccomp 环境，无需换机。

### 当前状态（起点）
- Stage 1 代码已在 main：`hatchery/sandbox_linux.py`（opt-in，默认关）、
  `_sandbox_worker` 接线、探针测试 `tests/test_sandbox_seccomp.py`（CI 上跳过）。
- 已收集的 runner 诊断数据：最小过滤器（arch+ALLOW）安装成功且放行一切；
  含 nr 匹配的过滤器被 EINVAL；完整过滤器安装成功但拒绝一切（含只读）。
  三变体诊断测试已写入 tests/test_sandbox_seccomp.py，等待真实 Linux 运行。

### 接手步骤
1. 安装 WSL2（本机）或使用任意 Linux VM/物理机；`pip install pytest`
2. `python -m pytest tests/test_sandbox_seccomp.py -v` 运行三变体诊断
   （diag-arch-match / diag-openat-any / diag-openat-writeflag）
3. 依据结果分流：
   a. 三变体全部按预期 → runner profile 问题实锤；`apply_sandbox_hardening`
      默认改回 on（去掉 opt-in），更新 R4_SANDBOX.md，Stage 1 完全关闭
   b. diag-arch-match 异常 → seccomp_data.arch 偏移/常量问题，复查编码
   c. diag-openat-any 异常 → nr 匹配链问题，复查 JEQ 跳转算术
   d. 仅 diag-openat-writeflag 异常 → 0x643 掩码 AND/JEQ 链问题
4. 修复后全量回归（195+ 测试）；PR + CI
5. 后续：Stage 2 Landlock（Linux 内核 5.13+）+ Windows Job Objects（本机 ctypes 可做）

### 本机可做（Windows，无需 Linux）
- 种子引导模板的转义卫生：`r'\[...` 与 `\s` 的 SyntaxWarning（-W error 时失败；
  种子功能不受影响，纯卫生）。根因在 incubator 模板的多层转义发射链，
  需配合 strace/compile 逐层定位。

---

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
