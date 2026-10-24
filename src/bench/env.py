"""Capture everything needed to reproduce / sanity-check a run."""
import datetime
import os
import platform
import subprocess
import sys


def _read(path: str, default: str = "") -> str:
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return default


def capture_env() -> dict:
    cpu = next((l.split(":", 1)[1].strip() for l in _read("/proc/cpuinfo").splitlines()
                if l.startswith("model name")), "unknown")
    mem = next((int(l.split()[1]) for l in _read("/proc/meminfo").splitlines()
                if l.startswith("MemTotal:")), 0)
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             timeout=5).stdout.strip()
    except Exception:
        sha = ""
    return {"cpu_model": cpu, "nproc": os.cpu_count(), "mem_total_kib": mem, "kernel": platform.release(),
            "governor": _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor").strip(),
            "loadavg_1m": os.getloadavg()[0], "python": sys.version.split()[0], "git_sha": sha,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
