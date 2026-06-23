# Glossary — metaphor ↔ mechanism

Progenitor is described in deliberately biological language ("digital primordial life"). That
persona is intentional, but it can over-promise. This table pins each metaphor to **what the code
actually does**, so nobody mistakes a label for a capability. When the two ever drift apart, the
mechanism column is the truth. See also [VISION.md](VISION.md) (direction) and [REVIEW.md](REVIEW.md) (evidence).

| Term (persona) | What the code actually does |
|---|---|
| **Progenitor / `.pgn` seed** | A single self-contained Python file that bootstraps the engine. "Self-bootstrapping," **not** self-rewriting — it reconstructs and runs its own embedded payload; it does not modify its own logic. |
| **gene** | A capability module. Under Gene Contract v2 a gene declares `purity` (pure/effectful) + `grants`; its output is an **advisory proposal**, never auto-applied. |
| **evolution / 进化 / `EvolutionTracker`** | A **lifecycle phase label** derived purely from a usage counter: `mutation` (usage < 5) → `adaptation` (usage ≥ 5) → `evolution` (usage ≥ 5 *and* ≥1 logged innovation), plus a score. **No code self-modification and no machine learning** — crossing into `evolution` only emits a "consider packaging a new version" hint. |
| **innovation / `log_innovation`** | A manually recorded note that an innovation happened (it nudges the phase). It is *logged*, not auto-detected. |
| **memory / 记忆 / `CrystallizedPersistence`** | **Checksummed state persistence** across process restarts (`hibernate` saves a JSON snapshot of tracker/logs/metadata; `resurrect` reloads it). It is saved *state*, **not** learned memory and not an ML model. |
| **pulse / heartbeat / 代谢心跳** | A host-invoked tick: increments the usage counter, persists state if it changed, optionally runs idle introspection. It runs when the host calls it — there is no background thread evolving on its own. |
| **phagocytosis / 胞吞 / `phagocytize`** | Fetch a gene by content address and verify its SHA-256 — a pull-and-verify, nothing more. |
| **infection / spore / 孢子** | **Opt-in, consent-gated** propagation transports (file / UDP / IPFS). Nothing self-installs or auto-executes on a peer; see voluntary adoption below. |
| **voluntary adoption** | `discover → inspect → host decides → cache` (`hatchery/adoption.py`). The engine **never** auto-infects or auto-runs a fetched gene; the host (agent + human) decides. |
| **Akashic / 阿卡夏 / registry** | A content-addressed, signed, lineage-traceable **capability ledger**. A collective *record* with provenance — **not** collective learning or a mystical shared mind. |
| **crucible / lysosome** | A security **audit + AST denylist pre-filter** (a speed bump, not a sandbox boundary) plus the Gene Contract v2 AST allowlist for pure genes. |
| **TelomereGuard** | Resource caps (time/memory) on the out-of-process gene sandbox (Unix). |
| **trust_state / web-of-trust** | Provenance labels backed by signatures: `registry_verified` (gatekeeper vouched) or `creator-signed:<owner>` (a keyring-trusted creator signed the exact content). |

## The honest summary

Progenitor **does**: package a capability as one portable file, content-address and sign it,
fetch-and-verify it, scope its execution, and let a host voluntarily adopt it. Progenitor **does
not**: rewrite its own code, learn from data, evolve autonomously in the background, or infect
peers without consent. The biology is the story; this table is the spec.
