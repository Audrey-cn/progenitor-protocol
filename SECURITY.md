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

## Supported versions

Only `main` is supported; there are no released/maintained versions yet.
