#!/usr/bin/env python3
"""Kill leftover chromium processes from earlier probe runs.

Excludes this process and its ancestors so the script cannot kill itself.
"""
import os
import subprocess
import time


def pids() -> list:
    out = subprocess.run(["pgrep", "-f", "chrome-linux64/chrome"],
                         capture_output=True, text=True).stdout
    return [int(x) for x in out.split() if x.strip().isdigit()]


def ancestors() -> set:
    keep = {os.getpid()}
    p = os.getppid()
    while p > 1 and p not in keep:
        keep.add(p)
        try:
            with open(f"/proc/{p}/stat") as f:
                parts = f.read().rsplit(")", 1)[1].split()
            p = int(parts[1])
        except Exception:
            break
    return keep


keep = ancestors()
victims = [p for p in pids() if p not in keep]
for p in victims:
    try:
        os.kill(p, 9)
    except Exception:
        pass
time.sleep(2)
print("killed:", len(victims))
print("remaining:", len([p for p in pids() if p not in ancestors()]))
