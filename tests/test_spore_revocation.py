"""R5.5: spore consent revocation - withdraw a granted consent, stop the beacon,
and confirm the propagation gate re-closes."""
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "hatchery"))

import engine  # noqa: E402


def _daemon():
    return engine.SporeDaemon()


def test_revoke_after_grant_stops_everything():
    d = _daemon()
    grant = d.grant_consent()
    assert grant["status"] == "consent_granted"
    assert d._consent_given is True
    revoked = d.revoke_consent()
    assert revoked["status"] == "consent_revoked"
    assert revoked["was_granted"] is True
    assert d._consent_given is False
    assert d._consent_explicitly_denied is False  # revoked != denied: no nagging
    assert d._available_channels == []


def test_revoke_without_prior_grant_is_honest():
    d = _daemon()
    revoked = d.revoke_consent()
    assert revoked["status"] == "consent_revoked"
    assert revoked["was_granted"] is False


def test_revoked_daemon_refuses_to_share(tmp_path):
    d = _daemon()
    d.grant_consent()
    d.revoke_consent()
    gene = tmp_path / "g.py"
    gene.write_text("def main():\n    return 1\n", encoding="utf-8", newline="")
    result = d.auto_disseminate(str(gene), "some-gene")
    assert result["status"] == "consent_required", result


def test_revoke_is_quiet_no_reminder_nagging():
    d = _daemon()
    d.grant_consent()
    d.revoke_consent()
    # 撤销不是拒绝：不应触发"再来一次"提醒循环
    assert d.on_innovation(99) is None


def test_regrant_after_revoke_works():
    d = _daemon()
    d.grant_consent()
    d.revoke_consent()
    grant = d.grant_consent()
    assert grant["status"] == "consent_granted"
    assert d._consent_given is True
