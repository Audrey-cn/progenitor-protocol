"""Spore tests against the REAL engine.SporeDaemon.

Previously this file asserted on a hardcoded CHANNELS dict and tautologies. It now drives
the real SporeDaemon: consent gating, channel detection, deny logic, and the file-spore drop.
"""
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "hatchery"))

import engine


def test_consent_required_by_default():
    sd = engine.SporeDaemon()
    result = sd.auto_disseminate("/tmp/whatever", "demo-gene")
    assert result["status"] == "consent_required"


def test_detect_channels_includes_file_and_udp():
    sd = engine.SporeDaemon()
    sd._detect_channels()
    names = [c[0] for c in sd._available_channels]
    assert "file_spore" in names
    assert "udp_beacon" in names


def test_deny_consent_increments_count():
    sd = engine.SporeDaemon()
    first = sd.deny_consent()
    assert first["status"] == "consent_denied" and first["deny_count"] == 1
    assert sd.deny_consent()["deny_count"] == 2


def test_no_reminder_without_denial():
    sd = engine.SporeDaemon()
    # neither granted nor denied → no nagging
    assert sd.on_innovation(5) is None


def test_grant_consent_enables(monkeypatch):
    sd = engine.SporeDaemon()
    monkeypatch.setattr(sd._beacon, "start", lambda: None)  # don't bind a real UDP socket
    result = sd.grant_consent()
    assert result["status"] == "consent_granted"
    assert sd._consent_given is True


def test_file_spore_drop_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    src = tmp_path / "gene_src"
    src.write_text("# life_id: PGN@L1-G1-X\ndef main():\n    return 1\n", encoding="utf-8")
    spore_path = engine._drop_spore_file(str(src), "demo-gene")
    assert spore_path is not None
    assert Path(spore_path).exists()
