"""Strix / Cloudflare Security Audit ve Snyk ToxicSkills Karantina Denetçisi."""
import os
import re
from typing import Any, Dict, List


DANGEROUS_CODE_PATTERNS = [
    ("HARDCODED_SECRET", re.compile(r"(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,})")),
    ("UNSAFE_EVAL_EXEC", re.compile(r"\b(?:eval|exec)\s*\(")),
    ("SUBPROCESS_SHELL_TRUE", re.compile(r"subprocess\.[a-zA-Z_]+\([^)]*shell\s*=\s*True")),
]

TOXIC_SKILL_PATTERNS = [
    (
        "PROMPT_INJECTION_OVERRIDE",
        re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.I),
    ),
    (
        "ENV_SECRET_EXFILTRATION",
        re.compile(
            r"(?:curl|wget|fetch).*?(?:\.env|auth\.json|id_rsa|API_KEY)", re.I | re.S
        ),
    ),
    ("HIDDEN_BASE64_PIPE_SH", re.compile(r"base64\s+-d\s*\|\s*(?:ba)?sh", re.I)),
]


def run_defensive_security_audit(src_root: str) -> Dict[str, Any]:
    """Uygulama kaynak kodunu zafiyet desenlerine karşı tarar."""
    critical_findings: List[Dict[str, Any]] = []
    scanned_files = 0

    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".git"}]
        for fname in sorted(filenames):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            if fname == "security_audit.py":
                continue
            scanned_files += 1
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except OSError:
                continue

            for rule_name, regex in DANGEROUS_CODE_PATTERNS:
                for match in regex.finditer(content):
                    critical_findings.append(
                        {
                            "file": fpath,
                            "rule": rule_name,
                            "snippet": match.group(0)[:80],
                        }
                    )

    return {
        "status": "PASS" if not critical_findings else "FAIL",
        "scanned_files": scanned_files,
        "critical_findings": critical_findings,
    }


def audit_skill_markdown(markdown_text: str) -> Dict[str, Any]:
    """Dış ekosistemden indirilen SKILL.md metnini Snyk ToxicSkills kurallarıyla denetler."""
    reasons: List[str] = []
    for rule_name, regex in TOXIC_SKILL_PATTERNS:
        if regex.search(markdown_text):
            reasons.append(rule_name)

    return {
        "verdict": "SAFE" if not reasons else "QUARANTINED",
        "reasons": reasons,
    }
