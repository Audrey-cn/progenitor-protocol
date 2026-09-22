# Security Policy

Progenitor is an **experimental research project**. Treat it accordingly — see
[Is it safe?](README.md#-is-it-safe) and the evidence-based [Engineering Review](docs/REVIEW.md).

## Reporting a vulnerability

Open a [GitHub issue](https://github.com/Audrey-cn/progenitor-protocol/issues) (or contact the
maintainer privately for sensitive reports). This is research code — there is no SLA.

## Known limitations (by design / not yet hardened)

- **Non-Unix resource caps are best-effort.** \TelomereGuard\'s wall-clock cap is a hard\
  interrupt on Unix (SIGALRM); elsewhere it is a sys.monitoring soft cap (Python 3.12+) that fires\
  on the next executed line, and there is no memory cap off-Unix. Untrusted genes still belong in a VM/container.
- **Gene execution is screened, not hard-sandboxed.** The AST dangerous-call denylist is a
  *pre-filter, not a security boundary*, and gene code runs in a subprocess with **your**
  privileges. Untrusted gene execution is **off by default** (`PROGENITOR_ALLOW_GENE_EXEC=1`
  to opt in). Run untrusted genes in a throwaway VM/container.
- **The registry index is signed, and the engine verifies it (closed F006).** The engine fetches and
  verifies \.akashic_index.json.sig\ (RSA-SHA256) against a hard-coded default key or the\
  \PROGENITOR_REGISTRY_PUBLIC_KEY\ override before trusting the index (strict by default,\
  \PROGENITOR_INDEX_SIGNATURE_MODE\ to change). Per-creator trust additionally uses the registry
  keyring (\PROGENITOR_TRUST_KEYRING[_FILE]\) with signed genes upgrading \	rust_state\.
- See [docs/REVIEW.md](docs/REVIEW.md) for the full security findings and their status.

## Converging your trust ring (reduce single-point trust)

The default keyring hard-codes the founder's public key - that is a single point of trust.
Hosts SHOULD converge it to their own explicit trust set:

```bash
# 1. Export your trusted signers' public identities into a keyring file:
#    {"trusted_keys": [{"owner": "...", "public_key": {...}}, ...]}
# 2. Point the engine at it:
set PROGENITOR_TRUST_KEYRING_FILE=path/to/trusted_keys.json
# 3. Optionally narrow further (comma-separated owners/key_ids):
set PROGENITOR_TRUST_SET=YourName
```

With a converged ring, only genes signed by YOUR trusted set upgrade to
`creator-signed:<owner>`; everything else stays untrusted regardless of registry status.

## Known gap: spore consent is one-way

Spore propagation consent is a one-time, global flag with **no revoke/withdraw mechanism**
(code audit 2026-09-22: zero revoke/withdraw implementations). Treat consent as permanent
for the process lifetime; run in a disposable environment if this is unacceptable.
Scheduled for hardening - see [EXTERNAL_REVIEW_SIMULATION.md](docs/EXTERNAL_REVIEW_SIMULATION.md) R5.

## External review simulation

The harshest third-party-perspective audit of this project is checked in at
[EXTERNAL_REVIEW_SIMULATION.md](docs/EXTERNAL_REVIEW_SIMULATION.md) - read it before
trusting any claim in this README.

## Supported versions

Only `main` is supported; there are no released/maintained versions yet.
