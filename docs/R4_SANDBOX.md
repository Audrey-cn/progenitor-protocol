# R4 — OS-Level Sandbox Hardening (design)

Status: **design approved, Stage 1 pending implementation** (2026-09-22). This doc turns the
long-line "OS-level sandbox" backlog item into staged, verifiable increments. It complements —
never replaces — the standing advice: **run untrusted genes in a VM/container**.

## Threat model (what "sandboxed" must mean here)

A gene granted `effectful` execution must not be able to, beyond its declared grants:
1. touch the filesystem outside an explicit cache dir (no reads of host secrets, no writes),
2. open network connections unless `net` grants say so,
3. spawn processes or load kernel interfaces,
4. exhaust host resources (CPU/mem/time) — TelomereGuard covers time (Unix hard, 3.12+ soft),
   RLIMIT_AS covers memory (Unix only).

## Current state (honest)

| Layer | Mechanism | Verdict |
|---|---|---|
| Static | AST allowlist + curated builtins (`capability.py`) | strong **pre-filter**, porous in-process |
| Dynamic | `execute_gene_in_sandbox`: subprocess + TelomereGuard (SIGALRM+RLIMIT_AS Unix; sys.monitoring soft cap elsewhere) | process boundary only — child runs with **full host privileges** |
| Default posture | untrusted gene **execution refused** (`PROGENITOR_ALLOW_GENE_EXEC=1` to opt in) | honest; keep forever |

## Options evaluated (iron rule: Python stdlib only — ctypes to the kernel is allowed, third-party packages are not)

| Option | Platform | Stdlib-able | Isolation strength | Verdict |
|---|---|---|---|---|
| **seccomp-BPF denylist** (prctl `NO_NEW_PRIVS` + socket/connect/execve/openat-write filter) | Linux | ✅ ctypes raw BPF | syscall-level: kills network/exec/write escapes | **Stage 1** |
| **Landlock ruleset** (kernel 5.13+) | Linux | ✅ ctypes, ABI probe | FS read/write/execute scoping, no caps needed | **Stage 2** (finer FS than seccomp) |
| **user namespaces** (`unshare(CLONE_NEWNET\|NEWNS\|NEWPID)`) | Linux | ✅ ctypes (or `unshare(1)` subprocess) | strongest (net+mount+pid), distro-dependent user-ns policy | **Stage 3** (best-effort detect + use) |
| **Windows Job Objects** (kernel32 via ctypes: mem limit, CPU-time limit, kill-on-close) | Windows | ✅ ctypes | restores **resource caps** parity (time+mem) on Windows | **Stage 2b** |
| **wasm** (wasmtime/…) | any | ❌ third-party | strongest in-process | host-optional sidecar; never engine core |
| VM/container | any | out of scope | strongest | standing advice for genuinely hostile genes |

## Staged plan

### Stage 1 — Linux syscall denylist in the sandbox preexec (CI-verifiable)
- New `hatchery/sandbox_linux.py`: `apply_seccomp_denylist(spec)` — `prctl(PR_SET_NO_NEW_PRIVS)` +
  BPF program denying `socket`/`socketpair`/`connect`/`execve`/`execveat` (and write-flagged
  `openat` when grants exclude `fs:write`), via `ctypes` + `syscall(317/PR_SET_SECCOMP)`.
- Wired into `execute_gene_in_sandbox`'s POSIX preexec (after RLIMIT setup), activated for
  untrusted/limited-trust genes; `PROGENITOR_SANDBOX_SECCOMP=off` escape hatch (default on Linux).
- **Exit criterion (test on ubuntu CI):** a gene whose `main()` calls `socket.socket().connect()`
  raises/gets EPERM inside the sandbox while a benign pure gene is unaffected; both still
  hash-verified through `acquire_gene`.
- Verifiable only on Linux CI (dev box is Windows) — implementation lands with CI green as the gate.

### Stage 2 — Landlock FS scoping (Linux) + Windows Job Objects
- Landlock: ruleset allows read-only over the gene's own cache paths; everything else denied.
  ABI probe → graceful skip on older kernels.
- Windows: Job Objects via ctypes for `execute_gene_in_sandbox` — memory limit + user-mode CPU
  time + kill-on-job-close; removes the last honest "no mem/time caps on Windows" caveat.
- **Exit criterion:** sandbox test suite green on ubuntu + windows CI matrices with caps enforced.

### Stage 3 — namespace hardening (best-effort)
- Detect `CLONE_NEWNET` availability; when usable, spawn the sandbox inside a net+mount namespace
  so seccomp becomes belt-and-suspenders rather than the only wall.

## Non-goals
- No third-party isolation runtimes in the engine core (wasm stays a host-optional adapter).
- No silent capability escalation: a grant always maps to an explicit host decision
  (Gene Contract v2 / `adoption.py`), the sandbox only enforces what was granted.
