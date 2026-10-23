#!/usr/bin/env python3
"""Sıfır-Token Sessiz Altyapı Watchdog Betiği (`no_agent=True` Cronjob için)."""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, "/root/ai_browser_farm")
from src.devtools.self_evolution_engine import evaluate_silent_watchdog


def main() -> int:
    usage = shutil.disk_usage("/root")
    free_gb = usage.free / (1024 ** 3)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "/root/ai_browser_farm/tests",
            "-t",
            "/root/ai_browser_farm",
        ],
        cwd="/root/ai_browser_farm",
        capture_output=True,
        text=True,
    )
    failed_tests = 0 if proc.returncode == 0 else 1

    alert = evaluate_silent_watchdog(
        disk_free_gb=free_gb,
        failed_tests=failed_tests,
        unhealthy_services=[],
    )
    if alert:
        print(alert)
    return 0


if __name__ == "__main__":
    sys.exit(main())
