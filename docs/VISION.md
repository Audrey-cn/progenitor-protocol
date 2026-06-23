# Vision — the North Star

This is the corrected direction for Progenitor, and the reference all future iteration
checks against. It supersedes the original "digital virus that auto-infects and evolves"
framing. For current status see [ROADMAP.md](ROADMAP.md); for the evidence base see [REVIEW.md](REVIEW.md).

## The one-line correction

> From **"a virus that autonomously infects agents and rewrites itself"**
> to **"frictionless propagation + verifiable provenance + scoped execution + voluntary adoption"** —
> a decentralized, content-addressed, signed way for AI agents to *share and safely run* skills.

"Viral" autonomous infection + auto-execution of arbitrary peer code is fundamentally at
odds with trust, and we deliberately do **not** pursue it. But the *valuable* core of a virus —
**propagating with zero friction and carrying everything it needs in one self-contained unit** —
is real, achievable, and largely already built. We keep that, and add what makes it trustworthy.

## What "Akashic" actually means here

The Registry is not a mystical memory; it is a concrete, honest artifact:

> **A content-addressed, signed, lineage-traceable shared capability ledger.**

- **Content-addressed** — a gene *is* its SHA-256; name → hash → verified bytes.
- **Lineage** — every gene carries a `PGN@` ancestry (`life_id`), so provenance is traceable.
- **Signed** — the index is signed (`.akashic_index.json.sig`, RSA-SHA256); authenticity is verifiable.

The poetic parts ("collective memory", "evolution") are honestly downgraded: today the ledger
is a collective *record*, not collective *learning*; lifecycle "phases" are usage labels, not
code mutation. We either make those real later or keep them labeled as what they are.

## Where we are vs what we build

**✅ Foundation (done):** single-file self-bootstrap (`curl | python3` works), content-addressing,
signed index, multi-path transport (GitHub raw · IPFS · LAN spores), green CI + release gate.

**🔨 Three pillars to build:**

| Pillar | Repo | Why |
|---|---|---|
| **A. Trusted provenance** | Registry | know *what* you pulled and *who* published it |
| **B. Scoped execution** *(keystone)* | Protocol | safely *run* a stranger's skill |
| **C. Voluntary adoption** | Protocol | the host agent *decides*, nothing auto-infects |

## The virus → trusted-propagation reframe

| Virus (unsafe) | What we build instead |
|---|---|
| auto-infect & execute arbitrary peer code | **content-address + signature** → you know what it is and who signed it |
| in-process denylist as the backstop | **capability scope + AST allowlist sandbox** (enforceable, unlike a denylist) |
| host is silently colonized | **adoption is the agent's decision**, gated by manifest + provenance + reputation |

## Gene Contract v2 — the keystone design

The single change that unlocks free exchange: **a gene is a declared, mostly-pure capability
whose output is a *proposal*; the host agent decides whether to act on it.** This turns the
unsolvable problem ("sandbox arbitrary untrusted code") into a solvable one ("run a declared
function with no ambient authority").

```text
# capability manifest (gene header)
# life_id:   PGN@L1-G3-CODE-REVIEWER
# creator:   Audrey
# purity:    pure            # pure | effectful
# inputs:    code: str
# outputs:   issues: list, score: int
# grants:    []              # effectful genes must declare, e.g. [net:github.com, fs:read]
---
def main(code: str) -> dict:
    ...
    return {"issues": [...], "score": 90}   # ADVISORY — the host decides what to do with it
```

- **`pure` genes** run under an **AST allowlist** (arithmetic, string/list/dict ops, a small set
  of declared stdlib like `json`/`re`/`math`; **no** `import os`/`socket`/`subprocess`, **no** dunder
  attribute access), with resource caps. No ambient authority → safe to run from anyone.
- **`effectful` genes** must declare `grants`; each grant requires explicit host consent, and the
  result is still advisory.
- The engine **returns the result to the host agent** — it does not auto-apply side effects. This
  is the technical meaning of "voluntary adoption": skills propose, the agent (and human) dispose.

> Allowlist, not denylist: an allowlist is *enforceable*; the denylist we shipped is a speed bump.
> Real OS/wasm isolation (seccomp/landlock/wasm) is a later hardening, not a blocker for `pure` genes.

## Positioning — the defensible niche

Next-gen agent skill exchange today is mostly **centralized + platform-bound** (MCP servers,
per-vendor skill stores). Progenitor's defensible angle:

- **trust the hash + signature, not a platform** (content-addressed, signed ledger);
- **one zero-dependency file, any host** (`curl`-installable — lighter than MCP);
- **multi-path transport** (GitHub / IPFS / LAN — censorship- and single-point-resistant).

In one phrase: **BitTorrent + signatures + self-bootstrap, for agent skills.**

## Iteration roadmap

1. **Keystone · Protocol — Gene Contract v2:** capability manifest + pure/advisory execution +
   AST-allowlist sandbox; per-capability grants replace the global exec gate. Tests: pure gene
   runs but can't touch fs/net; effectful refused without grant; escape payloads blocked.
   *Status (2026-06-23): ✅ landed* — `hatchery/capability.py` (manifest + `check_pure_safe`
   AST allowlist + advisory `run_pure_gene` with a SIGALRM wall-clock cap); `Phagocyte.express_gene`
   routes by declared purity (pure runs with no opt-in; effectful requires per-capability grant
   consent via `grants=...`, else `ungranted`); registry **L6** rejects genes that claim
   `purity: pure` but violate the allowlist (the two repos are converged on the contract).
   *Deferred hardening:* memory caps on the pure path need the out-of-process sandbox (the
   allowlist already denies all I/O); real OS/wasm isolation remains future work for effectful genes.
2. **Registry — web-of-trust provenance:** per-creator signing (not only the founder) + a
   configurable trust set; surface reputation from `.gene_score_log`. Makes the ledger truly collective.
   *Status (2026-06-23): ✅ landed* — registry `policy/trusted_keys.json` keyring + `tools/trust.py`
   (configurable trust set via `PROGENITOR_TRUST_SET`; verify against trusted keys, never the
   embedded one) + `tools/trust_report.py` (signer + per-gene trust/reputation view); creators sign
   their genes via `tools/sign_gene.py` → gatekeeper upgrades `trust_state` to `creator-signed:<owner>`;
   the protocol engine verifies the index against a **keyring** (`PROGENITOR_TRUST_KEYRING[_FILE]`),
   trust anchor pinned locally. *Deferred:* a real reputation signal (scores are seeded at 0 today).
3. **Protocol — voluntary adoption + federation:** explicit `discover → inspect → host decides →
   cache` flow (no auto-infect); LAN → optional WAN (IPFS pin / relay).
   *Status (2026-06-23): adoption ✅ landed* — `hatchery/adoption.py` (`inspect` → `decide` →
   `adopt`, pure/offline, **never executes**; hard-rejects hash mismatch / invalid signature /
   flagged reputation; caches content-addressed only on explicit host approval) + `Phagocyte.
   propose_adoption` / `adopt_gene`. *Remaining:* WAN federation — formalize the transport-hint
   ladder (registry → github_raw → IPFS → LAN peer) and IPFS pin/relay as an opt-in tier (the
   multi-path transports + IPFS publish already exist; this is wiring + real-network testing).
4. **Ongoing — honesty in code:** rename `self-evolution` → lifecycle phases; make "memory" a real
   (small) learned-preference store or keep it labeled "state".
   *Status (2026-06-23): ✅ landed (honest-labeling branch)* — [GLOSSARY.md](GLOSSARY.md) pins every
   persona term to its real mechanism (evolution = usage-driven lifecycle phase label, no code
   self-modification / no ML; memory = checksummed state persistence, not learned memory), with
   honesty notes in the `EvolutionTracker` / `CrystallizedPersistence` docstrings. Persona kept,
   claims made truthful. *Optional future:* turn "memory" into a small real learned-preference store.

## Non-goals (deliberately)

- Autonomous infection or auto-execution of untrusted peer code.
- Claiming self-evolution / code generation we don't do.
- A single central authority for trust (use signatures + a trust graph instead).
