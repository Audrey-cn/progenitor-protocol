# Security Policy

Progenitor is an **experimental research project**. Treat it accordingly — see
[Is it safe?](README.md#-is-it-safe) and the evidence-based [Engineering Review](docs/REVIEW.md).

## Reporting a vulnerability

Open a [GitHub issue](https://github.com/Audrey-cn/progenitor-protocol/issues) (or contact the
maintainer privately for sensitive reports). This is research code — there is no SLA.

## Known limitations (by design / not yet hardened)

- **Gene execution is screened, not hard-sandboxed.** The AST dangerous-call denylist is a
  *pre-filter, not a security boundary*, and gene code runs in a subprocess with **your**
  privileges. Untrusted gene execution is **off by default** (`PROGENITOR_ALLOW_GENE_EXEC=1`
  to opt in). Run untrusted genes in a throwaway VM/container.
- **The registry index is not yet signed.** Gene content is SHA-256-verified against the index,
  but a tampered index could swap both the CID and its expected hash. Index signing is on the roadmap.
- See [docs/REVIEW.md](docs/REVIEW.md) for the full security findings and their status.

## Supported versions

Only `main` is supported; there are no released/maintained versions yet.
