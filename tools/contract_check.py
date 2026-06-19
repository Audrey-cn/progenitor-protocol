import json

from repo_paths import PROTOCOL_DIR, REGISTRY_DIR

CONTRACT_FILE = PROTOCOL_DIR / "docs" / "PROTOCOL_CONTRACT.json"


def require(condition, message, failures):
    if not condition:
        failures.append(message)


def file_contains(path, needle):
    return path.exists() and needle in path.read_text(encoding="utf-8", errors="ignore")


def main():
    failures = []

    with open(CONTRACT_FILE, "r", encoding="utf-8") as f:
        contract = json.load(f)

    principles = contract.get("principles", {})
    require(principles.get("open_authorship") is True, "contract must preserve open_authorship=true", failures)
    require(principles.get("creator_whitelist_required") is False, "contract must not require creator whitelist", failures)
    require(principles.get("stdlib_only") is True, "contract must preserve stdlib_only=true", failures)
    require(principles.get("review_before_execution") is True, "contract must require review_before_execution", failures)

    for rel in contract["repositories"]["protocol"]["required_files"]:
        require((PROTOCOL_DIR / rel).exists(), f"missing protocol required file: {rel}", failures)

    for rel in contract["repositories"]["registry"]["required_files"]:
        if rel.endswith("/*"):
            require((REGISTRY_DIR / rel[:-2]).exists(), f"missing registry required dir: {rel}", failures)
        else:
            require((REGISTRY_DIR / rel).exists(), f"missing registry required file: {rel}", failures)

    gatekeeper = REGISTRY_DIR / ".github" / "workflows" / "gatekeeper.py"
    engine = PROTOCOL_DIR / "hatchery" / "engine.py"

    require(file_contains(gatekeeper, "ALLOWED_CREATORS = []"), "Gatekeeper must keep creator registry open", failures)
    require(file_contains(gatekeeper, "RATE_LIMIT_PER_PR"), "Gatekeeper must enforce L0 rate limit", failures)
    require(file_contains(gatekeeper, 'GATEKEEPER_STRICT_L2", "1"'), "Gatekeeper must fail closed on L2 content-address checks by default", failures)
    require(file_contains(gatekeeper, 'GATEKEEPER_STRICT_L4", "1"'), "Gatekeeper must fail closed on L4 quality checks by default", failures)
    require(file_contains(gatekeeper, "validate_l1_lineage"), "Gatekeeper must implement L1 lineage check", failures)
    require(file_contains(gatekeeper, "validate_l5_security"), "Gatekeeper must implement L5 security scan", failures)

    for symbol in contract["protocol_runtime_audit"]["entrypoints"]:
        require(file_contains(engine, f"def {symbol}"), f"engine missing runtime entrypoint: {symbol}", failures)

    require(file_contains(engine, "_quarantine_rejected_gene"), "engine must quarantine rejected genes", failures)
    require(file_contains(engine, 'SIGNATURE_MODE in {"required", "strict"}'), "engine signature required/strict modes must fail closed", failures)
    require(file_contains(engine, "TelomereGuard"), "engine must expose TelomereGuard runtime guard", failures)
    require(file_contains(engine, "isolated_run"), "engine must expose isolated_run sandbox path", failures)

    print("=" * 60)
    print("  Progenitor Contract Check")
    print("=" * 60)
    print(f"  contract: {CONTRACT_FILE}")

    if failures:
        for failure in failures:
            print(f"  ERROR: {failure}")
        return 1

    print("  OK: contract matches current repository structure and core review hooks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
