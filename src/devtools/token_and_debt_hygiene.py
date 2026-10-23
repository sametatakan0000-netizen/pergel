"""RTK / Caveman tarzı CLI çıktı sıkıştırıcı ve Ponytail `shortcut:` teknik borç tarayıcısı."""
import os
import re
from typing import Any, Dict, List


def compress_cli_output(raw_output: str, max_lines: int = 20) -> str:
    """Gürültülü CLI/test çıktılarını %60-90 oranında sıkıştırır, hata satırlarını korur."""
    lines = [line.rstrip() for line in raw_output.splitlines() if line.strip()]
    if len(lines) <= max_lines:
        return "\n".join(lines)

    priority_lines: List[str] = []
    normal_lines: List[str] = []
    critical_pattern = re.compile(
        r"(error|fail|exception|traceback|assert|warning|critical)", re.IGNORECASE
    )

    for line in lines:
        if critical_pattern.search(line):
            priority_lines.append(line)
        else:
            normal_lines.append(line)

    head_budget = max(2, (max_lines - len(priority_lines)) // 2)
    tail_budget = max(2, max_lines - len(priority_lines) - head_budget)

    head = normal_lines[:head_budget]
    tail = normal_lines[-tail_budget:] if tail_budget > 0 else []
    omitted_count = max(0, len(normal_lines) - len(head) - len(tail))

    result = list(head)
    if omitted_count > 0:
        result.append(f"... [{omitted_count} repetitive lines omitted by RTK hygiene] ...")
    result.extend(tail)
    result.extend(priority_lines)
    return "\n".join(result)


def scan_shortcut_debt(root_dir: str) -> List[Dict[str, Any]]:
    """Kod tabanındaki `# shortcut:` (Ponytail) ve `# TODO:` teknik borç kayıtlarını toplar."""
    pattern = re.compile(r"^\s*#\s*(shortcut|TODO)\s*:\s*(.+)$", re.IGNORECASE)
    debt_items: List[Dict[str, Any]] = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [
            d for d in dirnames if d not in {".git", "__pycache__", ".pytest_cache", "venv", ".venv"}
        ]
        for fname in sorted(filenames):
            if not fname.endswith((".py", ".sh", ".md", ".yaml", ".yml")):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    for lineno, line in enumerate(f, start=1):
                        match = pattern.search(line)
                        if match:
                            debt_items.append(
                                {
                                    "file": fpath,
                                    "line": lineno,
                                    "kind": match.group(1).lower(),
                                    "detail": match.group(2).strip(),
                                }
                            )
            except OSError:
                continue

    return debt_items
