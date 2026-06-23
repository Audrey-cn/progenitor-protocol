"""[adoption] Voluntary adoption pipeline — discover → inspect → host decides → cache.

docs/VISION.md, pillar C: skills propagate freely but are NEVER auto-infected. The host (agent +
human) inspects a candidate's provenance and capability scope, decides, and only then caches it.
Nothing here executes a gene — adoption is about acquiring + trusting, not running (running is
express_gene's job, and even that returns advisory results).

Composes the earlier pillars: content-addressing (verify the bytes), trust_state (pillar A,
provenance), purity/grants (pillar B, scope). Pure and offline by design — callers pass the
already-fetched bytes plus the registry index entry — so the decision logic is fully testable.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

try:
    from capability import parse_capability_manifest
except Exception:  # pragma: no cover - capability is a sibling module, present in the built seed
    parse_capability_manifest = None

TRUSTED_PROVENANCE = ("registry_verified",)  # creator-signed:* is also trusted (prefix match)


def inspect(gene_bytes, *, capability=None, index_entry=None, source=None, expected_sha256=None):
    """Build an adoption proposal from already-fetched bytes — no network, no execution."""
    index_entry = index_entry or {}
    sha = hashlib.sha256(gene_bytes).hexdigest()
    text = gene_bytes.decode("utf-8", errors="replace")
    manifest = parse_capability_manifest(text) if parse_capability_manifest else {"purity": "effectful", "grants": []}
    advertised = expected_sha256 or index_entry.get("content_sha256") or index_entry.get("expected_sha256")
    return {
        "capability": capability or index_entry.get("capability"),
        "content_sha256": sha,
        "size_bytes": len(gene_bytes),
        "creator": index_entry.get("creator", manifest.get("creator", "Anonymous")),
        "trust_state": index_entry.get("trust_state", "unverified"),
        "purity": manifest.get("purity", "effectful"),
        "grants": manifest.get("grants", []),
        "life_id": index_entry.get("life_id", manifest.get("life_id")),
        "source": source,
        "hash_verified": (advertised == sha) if advertised else None,
    }


def decide(proposal, *, require_pure=False, reputation=None):
    """Advisory recommendation for the host — never adopts, only suggests adopt / ask / reject.

    Hard reject: content hash mismatch, an invalid creator signature, or a flagged reputation.
    'ask' (human-in-the-loop) for untrusted provenance, effectful genes, or genes requesting
    grants. 'adopt' only for trusted provenance with no open questions. The host (and human) make
    the final call; this is guidance, not a gate — adoption still requires explicit approval.
    """
    ts = proposal.get("trust_state", "")
    if proposal.get("hash_verified") is False:
        return {"recommend": "reject", "reasons": ["content hash does not match the advertised hash"]}
    if ts.startswith("creator-signature-invalid"):
        return {"recommend": "reject", "reasons": ["invalid creator signature"]}
    if reputation == "flagged":
        return {"recommend": "reject", "reasons": ["capability is flagged in the reputation log"]}

    reasons = []
    trusted = ts.startswith("creator-signed") or ts in TRUSTED_PROVENANCE
    if not trusted:
        reasons.append(f"provenance '{ts or 'unknown'}' is not trusted")
    if require_pure and proposal.get("purity") != "pure":
        reasons.append("policy requires pure genes; this one is effectful")
    if proposal.get("purity") != "pure" and proposal.get("grants"):
        reasons.append("effectful — requests grants: " + ", ".join(proposal["grants"]))
    if reasons:
        return {"recommend": "ask", "reasons": reasons}
    note = "trusted provenance" + (", pure" if proposal.get("purity") == "pure" else "")
    return {"recommend": "adopt", "reasons": [note]}


def adopt(proposal, gene_bytes, cache_dir, *, approved):
    """Cache a gene ONLY on explicit host approval, content-addressed. Never executes it.

    Returns {"status": "adopted"|"refused"|"hash_mismatch", ...}. 'refused' if the host did not
    approve; 'hash_mismatch' if the bytes do not match the proposal's content_sha256.
    """
    if not approved:
        return {"status": "refused", "reason": "host did not approve adoption"}
    sha = hashlib.sha256(gene_bytes).hexdigest()
    if sha != proposal.get("content_sha256"):
        return {"status": "hash_mismatch", "expected": proposal.get("content_sha256"), "actual": sha}
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / sha
    path.write_bytes(gene_bytes)
    return {"status": "adopted", "path": str(path), "content_sha256": sha}
