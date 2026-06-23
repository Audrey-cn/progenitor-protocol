"""Engine web-of-trust: index signatures verify against a multi-key keyring (Iteration 2)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hatchery"))
import engine  # noqa: E402
import stargate_identity as si  # noqa: E402

ENVELOPE_BASE = {"schema_version": "akashic.index-signature/v1", "index_sha256": "deadbeef"}


def _signed_envelope(identity):
    return si.sign_document(dict(ENVELOPE_BASE), identity)


def test_default_keyring_is_founder_only(monkeypatch):
    monkeypatch.delenv("PROGENITOR_TRUST_KEYRING", raising=False)
    monkeypatch.delenv("PROGENITOR_TRUST_KEYRING_FILE", raising=False)
    ring = engine._load_trust_keyring()
    assert len(ring) == 1
    assert ring[0]["n"] == engine.AKASHIC_REGISTRY_PUBLIC_KEY["n"]


def test_unknown_signer_is_rejected(monkeypatch):
    monkeypatch.delenv("PROGENITOR_TRUST_KEYRING", raising=False)
    monkeypatch.delenv("PROGENITOR_TRUST_KEYRING_FILE", raising=False)
    stranger = si.generate_identity("stranger", bits=512)
    assert engine._verify_envelope_signature(_signed_envelope(stranger)) is False


def test_keyring_file_adds_trusted_creator(monkeypatch, tmp_path):
    creator = si.generate_identity("creator-x", bits=512)
    envelope = _signed_envelope(creator)
    # not trusted by default
    monkeypatch.delenv("PROGENITOR_TRUST_KEYRING", raising=False)
    monkeypatch.delenv("PROGENITOR_TRUST_KEYRING_FILE", raising=False)
    assert engine._verify_envelope_signature(envelope) is False
    # add the creator to a pinned keyring file → now trusted
    ring_file = tmp_path / "trusted_keys.json"
    ring_file.write_text(json.dumps({
        "trusted_keys": [{"owner": "CreatorX", "public_key": creator["public_key"]}]
    }), encoding="utf-8")
    monkeypatch.setenv("PROGENITOR_TRUST_KEYRING_FILE", str(ring_file))
    assert engine._verify_envelope_signature(envelope) is True


def test_keyring_env_list_adds_trusted_creator(monkeypatch):
    creator = si.generate_identity("creator-y", bits=512)
    envelope = _signed_envelope(creator)
    monkeypatch.delenv("PROGENITOR_TRUST_KEYRING_FILE", raising=False)
    monkeypatch.setenv("PROGENITOR_TRUST_KEYRING", json.dumps([{"public_key": creator["public_key"]}]))
    assert engine._verify_envelope_signature(envelope) is True
