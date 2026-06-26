# Akashic — Layered Architecture (the engineering north star)

This is the **engineering** companion to [VISION.md](VISION.md). VISION says *what* Akashic
is ("frictionless propagation + verifiable provenance + scoped execution + voluntary adoption").
This doc says *how the system is layered*, **which layer each existing file belongs to**, and —
critically — **which problems we deliberately do NOT solve ourselves** because a mature substrate
already solves them.

> **Snapshot of perspective — 2026-06-26.** This document also freezes the lens we are building
> with right now, on purpose. After the work below lands, we re-read this file top to bottom and
> ask the questions in [§7 Re-review checklist](#7-re-review-checklist) — to see what implementation
> taught us that this snapshot got wrong. Do not silently rewrite history here; append a dated
> "Re-review" section instead.

---

## 1. Why a layered model at all

The peer-to-peer "Akashic Stargate" stalled for one reason: **we were designing five layers at
once.** The transport/identity wire protocol, the object format, the agent handshake, the
evolution rules, and the trust graph were all in flight together, so no single one ever reached
"done and frozen."

The fix is to **separate the layers, borrow the bottom two, and concentrate original engineering
on the top three.** The bottom two (move bytes around, address an object) are solved problems
with decades of hardened prior art. The top three (how agents declare/negotiate capability, how a
capability earns or loses standing over time, how identity and trust compose without a central
authority) are where Akashic is actually novel — and where our time should go.

## 2. The five layers, mapped to real files

| Layer | Responsibility | Status | Where it lives today |
|---|---|---|---|
| **L1 · Network** | discover peers, move bytes, NAT traversal / relay | ⚠️ **the stalled layer** — pure-stdlib UDP discovery + HTTP gateway + IPFS gateway; no WAN traversal/relay | `hatchery/transport.py`, `hatchery/stargate_transport.py`, `engine.py` (UDP beacon, HTTP gateway) |
| **L2 · Object** | name and verify an immutable capability unit | ✅ **mature** — SHA-256 content-addressed genes + signed index | registry gene pool, `.akashic_index.json(.sig)`, `transport.resolve_transport` |
| **L3 · Agent** | declare capability, negotiate, adopt | ✅ landed — Gene Contract v2, `inspect → decide → adopt` | `hatchery/capability.py`, `hatchery/adoption.py`, `Phagocyte.express_gene` |
| **L4 · Evolution** | score, lineage, rollback, selection over time | ⚠️ **label-only** — lifecycle "phase" is a usage counter; scores seed at 0 | `engine.py` (`EvolutionTracker`), `.gene_score_log.json` |
| **L5 · Identity** | self-certifying node id, signing, web-of-trust | ✅ mostly landed — keyring, per-creator signing, TOFU trust store — **but node_id is not yet cryptographically bound to the key** | `hatchery/stargate_identity.py`, registry `policy/trusted_keys.json`, `tools/trust*.py`, `tools/stargate_resolver.py` |

**The honest read of this table:** the upper layers (L3/L5) are *more built* than the lowest one
(L1). The bottleneck was never "we haven't thought hard enough about the agent layer" — it was
that we tried to hand-build the network layer from scratch under a zero-dependency rule. See §4.

## 3. The core object-model insight: Akashic is Git, not Syncthing

The Syncthing comparison is what re-opened this direction, so be precise about what to borrow and
what to ignore.

Syncthing's hardest, largest body of code solves **mutable shared-folder sync**: two sides edit
the same file, so it needs version vectors, last-writer-wins, and `.sync-conflict` copies. **We do
not have that problem.** A gene is an **immutable, content-addressed object** — a hash either
matches or it doesn't; two genes are never "in conflict," they are simply two different hashes.
`transport.py` already states this philosophy: *content-addressing makes every path equally
trustworthy — a stranger's mirror is fine because the bytes are verified.*

So the correct mental model is **Git, not Syncthing**:

| Git | Akashic |
|---|---|
| immutable content-addressed **objects** (blobs/trees) | immutable content-addressed **genes** (SHA-256) |
| mutable signed **refs** pointing at objects | the signed **`.akashic_index.json`** (capability-name → current hash) |
| `git fetch` (dumb byte transfer, verified by hash) | `transport.resolve_transport` (hint ladder, verified by hash) |
| commit lineage / ancestry | gene `life_id` / `PGN@` lineage |

**What this lets us NOT build:** version vectors, conflict resolution, three-way merge, last-writer
-wins — the bulk of a sync engine. Immutability deletes that entire problem class. The only
"mutable" thing in the system is the **pointer** (the signed index / a peer manifest), and a
mutable signed pointer over immutable content is a *ref*, which is cheap and well-understood.

> Practical consequence: do not port Syncthing's Block Exchange Protocol or version-vector logic.
> Port its **identity model** (§4) and its **discovery model** (local broadcast + global/relay),
> nothing more.

## 4. The handshake unblock: self-certifying identity

`tools/stargate_resolver.py:handshake_peer` already does most of a real handshake: fetch `/hello`,
fetch a signed `/manifest`, verify the manifest signature against the advertised public key, store
the peer under trust-on-first-use, and reject a trusted peer whose key later changes. That is
already the Syncthing/libp2p trust model **in design**.

The missing keystone is that **`node_id` is an arbitrary string** (`local-gateway:9999`,
`stranger`, …) with **no cryptographic binding to the key**, and the advertised `public_key_id` is
taken on faith (never recomputed). The manifest signature proves *"I hold the private key for this
public key,"* but nothing proves *"this public key is node X"* — so a node id is forgeable.

**The fix (small code, large unblock):** make the node id *self-certifying*, exactly as Syncthing's
Device ID and libp2p's PeerID are:

```
node_id = fingerprint(public_key) = sha256(canonical_json(public_key))   # == public_key_id
```

Then a handshake adds two binding checks before trust:

1. `public_key_id == sha256(canonical_json(public_key))`  — the fingerprint is real, not asserted.
2. `node_id == public_key_id` (the node id *is* the fingerprint) — identity is unforgeable.

After this, "who is this peer" needs no central authority: the id **is** a verifiable claim, and
the only human decision left is the one we already gate (voluntary adoption / TOFU consent). Human
-friendly names move to a separate non-authoritative `label` field.

## 5. The decision that gates L1: zero-dependency core vs. sidecar substrate

Iron Rule #1 ("zero dependencies, stdlib only") is a strength in L3–L5 but it is what stalled L1,
and it has already produced real security debt in L5: `stargate_identity.py` hand-rolls **1024-bit
textbook RSA** with **no PKCS#1/PSS padding** (`pow(digest, d, n)` directly on the SHA-256 digest),
which has a known signature-forgery surface. NAT traversal + relay + a wire protocol + crypto are
precisely the lower-layer problems a zero-dep rule should *not* force us to reinvent.

**Recommended resolution — split the rule, don't break it:**

- **Engine core stays zero-dependency.** The always-available fallback path (LAN UDP discovery +
  HTTP gateway, pure stdlib) keeps `curl | python3` self-bootstrap intact. This is non-negotiable;
  it is the product's defining property.
- **L1/L5 expose an optional sidecar seam.** Behind the *interface we already have*
  (`resolve_transport(hints, expected_sha256, fetcher)` — a pluggable, injected fetcher), add
  adapters that ride a mature substrate when present: a libp2p / IPFS / Syncthing-relay transport,
  and an Ed25519 identity. The upper layers never learn which transport carried the bytes (content
  -addressing guarantees that doesn't matter) or which curve signed the manifest.

This is a genuine decision the project owner makes, recorded here so L1 work doesn't thrash:
**keep a zero-dep stdlib path that always works, and treat any heavier P2P/crypto substrate as an
optional adapter behind the transport/identity interface — never a hard dependency of the core.**

## 6. Where the real innovation is: L4

Git, IPFS, BitTorrent, and Syncthing all give you L1–L2 (and Git gives you a ref model for L2→L3).
**None of them give you L4.** Selection over capabilities — a gene earning standing through use,
accumulating lineage, and being rolled back or retired when it regresses — is the part of Akashic
that has no off-the-shelf equivalent. It is also the part [GLOSSARY.md](GLOSSARY.md) honestly marks
as label-only today (lifecycle "phase" is a usage counter; reputation scores seed at 0).

So the strategy is asymmetric on purpose:

- **L1–L2: freeze.** Pick the substrate decision in §5, finish self-certifying identity (§4), and
  stop touching these. They should become boring.
- **L3: stable, extend only as L4 demands.**
- **L4: invest here.** Real gene scoring → lineage record → rollback/retirement. This is the moat.
- **L5: finish the self-certifying binding, then pay down the RSA debt (§5) and leave it.**

## 7. Re-review checklist

Run this **after** the work above lands — with today's lens, deliberately preserved — and append a
dated "Re-review" section to this file with the answers.

1. **Did immutability really delete the sync problem (§3),** or did some workflow (e.g. mutable
   local working copies, or capability-name → hash races between peers) sneak a conflict problem
   back in at the *pointer* layer? If so, where, and is a ref-level resolution enough?
2. **Is the self-certifying id (§4) actually unforgeable end-to-end,** or did a legacy path
   (the UDP beacon's free-text `node_id`, an old trust record, the engine's `local-gateway:{port}`
   default) leave a gap where an unbound id is still trusted?
3. **Did the zero-dep/sidecar split (§5) hold,** or did the sidecar leak a hard dependency into the
   core / break `curl | python3`? Did we actually pay down the textbook-RSA debt, or just document it?
4. **Is L4 real now (§6),** or still a label with nicer words? Concretely: can a gene's score change
   from real usage, produce a lineage entry, and trigger a rollback — with a test that proves it?
5. **Did freezing L1–L2 stick,** or did we keep re-opening them and starve L4 again — the original
   failure mode?
6. **What did implementation reveal that this snapshot got wrong?** Name at least one assumption
   here that turned out false. (If we can't name one, we probably didn't look hard enough.)

---

## Re-review — 2026-06-26 (after the four pieces landed)

Done since the snapshot, each a separate tested step behind the green release gate (protocol **168
passed**, registry **42 passed**, seed still self-bootstraps): self-certifying identity (§4), the
transport/identity sidecar seams (§5), L4 `GeneLedger` with the adoption feedback loop (§6), and the
RSA hardening (§5). Answering the checklist with what the code now knows:

1. **Immutability deleted *object* conflicts, not *pointer* divergence.** The snapshot was right that
   genes never conflict — a hash matches or it doesn't. But the moment L4 introduced a per-capability
   *ref* (`capability → current hash`) that more than one peer can each advance, **Syncthing's
   conflict problem reappears at the pointer layer**: two peers can legitimately move "code-reviewer"
   to different hashes. Locally this is fine (the ledger is per-node); across peers it is an
   unsolved *ref reconciliation*. The good news is it reappears in a far more tractable form — over
   signed, lineage-carrying, reputation-scored pointers — so it is decidable, not a merge mess. **New
   work item: a federation ref-reconciliation policy (L4×L5).**
2. **The trust path is self-certifying end-to-end; the discovery path is not yet.** `handshake_peer`
   now binds node_id ⇒ key ⇒ signature, and forged ids are rejected (tested). Two legacy ids remain
   *unbound* but **cannot grant trust** because both fail the handshake gate: (a) the UDP
   `PassiveBeacon`'s free-text `node_id` (candidate-only discovery), and (b) the engine's `unsigned`
   fallback identity (`local-gateway:{port}`) served when key generation is unavailable. So the
   snapshot's "unforgeable end-to-end" was too strong: **trust is closed, discovery ids are still
   spoofable as labels.** **New work item: bind (or visibly mark unverified) discovery-layer ids.**
3. **The zero-dep/sidecar split held; the RSA debt was reduced, not eliminated.** Core stayed
   zero-dependency, the seed still `curl|python3`-activates, and the seams are pure additions (no
   sidecar shipped → no hard dep leaked). New signatures are now EMSA-PKCS1-v1_5 padded at 2048-bit,
   closing the forgery surface for *everything going forward* — every peer identity and manifest.
   But the legacy raw verifier is still registered, because the **committed registry index
   (`.akashic_index.json.sig`) was signed with the old scheme and can only be re-signed with the
   founder's private key.** **New work item (needs you): re-sign the registry index + genes with a
   padded key, then retire the raw verifier.**
4. **L4 is real for genes; the engine's own "phase" is still a label — by design.** A gene's score
   moves from real `express_gene` outcomes, each appends a lineage event, and a regression retires +
   rolls back the ref — proven end-to-end on real product code (`test_evolution_wiring`). The old
   `EvolutionTracker.phase` engine counter was left untouched: it was always about the *engine's*
   lifecycle, not *gene* selection, so it correctly stays a label. No overclaim added.
5. **Freezing L1–L2 mostly stuck.** The transport ladder and content-addressing core were not
   re-opened — the registry seam was purely additive. The identity/handshake touch (L1/L5) was
   necessary unblocking, not thrash. Crucially, the original failure mode (designing all five layers
   at once) did **not** recur: each layer shipped as an isolated, tested, green-gated step.
6. **Two assumptions the snapshot got wrong** (per its own honesty rule): (a) "Git not Syncthing → no
   conflict problem" is true only at the object layer — we *relocated* conflicts from bytes to
   pointers, we did not escape them; (b) "self-certifying ⇒ unforgeable end-to-end" overreached — only
   the trust path is closed, discovery ids remain unbound. Both corrections are now folded into the
   work items above.

**Net:** the headline bottleneck — the stalled P2P handshake — is unblocked at its root (forgeable
identity), and L4 (the moat) went from label to mechanism. The next frontier is explicitly
*federation*: ref reconciliation, discovery-id binding, and re-signing the trust anchor. These are
L4×L5 problems, which is exactly where the snapshot predicted the real work would concentrate.

### Follow-up — 2026-06-26 (same day): RSA hard cutover + trust-root rotation

Re-review item #3 is now **resolved**, by decision to accept a full refactor over a maintained
compatibility path:

- **Legacy raw scheme removed entirely.** `stargate_identity` ships exactly one signature scheme
  (EMSA-PKCS1-v1_5 padded RSA-SHA256). A signature claiming the retired `progenitor-rsa-sha256-v1`
  no longer verifies (tested). No dual-scheme maintenance surface remains.
- **Trust root rotated.** Because the old index was signed by a CI-only private key we don't hold,
  re-signing required minting a **new PKCS#1/2048 registry root**. The four anchors (engine default,
  resolver default, `policy/registry_public_key.json`, `policy/trusted_keys.json`) now carry the new
  key; `.akashic_index.json.sig` is re-signed with it; the engine verifies it under the new anchor
  end-to-end. The new private key is saved **only** to the gitignored
  `progenitor-registry/.registry_identity.SECRET.json`.
- **Open user action:** set that private identity as the CI secret `REGISTRY_PRIVATE_KEY_JSON`, store
  it securely offline, and treat the old published key as fully retired.

### Follow-up — 2026-06-26: federation pass (re-review #1 + #2 addressed)

- **#2 discovery-id binding — done.** `beacon_scan` now marks every discovered peer
  `id_verified: False` (a beacon node_id is a claim, not proof); `handshake_peer(expected_node_id=…)`
  binds that claim to the cryptographically-verified fingerprint and rejects a lying beacon
  (`peer_beacon_id_mismatch`); the unsigned gateway fallback identity is tagged `unverified: True`.
  The discovery path can no longer pass off an unbound id as trusted. Tested end-to-end on a real
  gateway + beacon.
- **#1 ref reconciliation — primitive done.** `hatchery/federation.py:reconcile_refs` resolves
  cross-peer pointer divergence by an explicit policy: drop retired (L4) and untrusted (L5)
  versions, rank by reputation then lineage, return a strict winner or flag genuine `diverged` for
  the host (never a silent pick). `candidate_from_ledger` feeds it straight from the GeneLedger.
  This is the local decision primitive; **still future transport work:** exchanging these candidate
  refs over the wire (peer manifests advertising per-capability lineage + reputation).

### Follow-up — 2026-06-26: federation wire exchange (the last piece)

Done over the **existing** HTTP transport (no new transport needed):
- **Serve side:** a `LocalGateway` with a `GeneLedger` attached now advertises each gene's
  first-hand `reputation` / `lineage_depth` / `retired` inside the **signed** peer manifest, so the
  numbers can't be tampered in transit.
- **Consume side:** `federation.reconcile_peer_manifests(manifests, peer_trust, local_ledger)` groups
  candidates per capability across peers + our own ledger and reconciles each. Crucially it gates by
  **our** trust in each advertising peer (`peer_trust`), *ignoring* a peer's self-advertised gene
  trust — an unknown peer defaults to `candidate` (excluded), so a stranger can't inject a winner by
  claiming trust or inflating reputation. Our own `local` evidence always counts.

Federation is now functionally closed end-to-end: self-certifying identity → signed manifest
carrying L4 evidence → trust-gated cross-peer reconciliation. Real-network hardening (multi-host
testing, IPFS/relay transports behind the §5 seam) remains, but the protocol is complete and tested
(protocol **184** / registry **42**).
