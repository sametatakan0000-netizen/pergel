#!/usr/bin/env python3
"""Sıfır-Token Sessiz Altyapı Watchdog Betiği (`no_agent=True` Cronjob için)."""
import os
import pathlib
import shutil
import subprocess
import sys

REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, REPO_ROOT)
from src.devtools.self_evolution_engine import evaluate_silent_watchdog


def main() -> int:
    usage = shutil.disk_usage(REPO_ROOT)
    free_gb = usage.free / (1024 ** 3)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            os.path.join(REPO_ROOT, "tests"),
            "-t",
            REPO_ROOT,
        ],
        cwd=REPO_ROOT,
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
