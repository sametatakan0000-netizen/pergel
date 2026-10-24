"""Live inspection driver: fills collect_live_info for installed targets.

Reads only what the OS and the engine itself expose (version strings, /proc, listening
sockets). No MITM, no page interception, no third-party calls.
"""
import glob
import os
import socket
import subprocess
import time
from typing import Dict, List

from src.bench.inspect import collect_live_info  # noqa: F401  (re-exported for tests)


def _listening_ports(pids: List[int]) -> List[str]:
    """Parse /proc/<pid>/net/tcp for LISTEN sockets (0A state), local port only."""
    ports = set()
    for pid in pids:
        for path in (f"/proc/{pid}/net/tcp", f"/proc/{pid}/net/tcp6"):
            try:
                with open(path) as fh:
                    next(fh, None)
                    for line in fh:
                        f = line.split()
                        if len(f) >= 4 and f[3] == "0A":
                            ports.add(int(f[1].rsplit(":", 1)[1], 16))
            except OSError:
                pass
    return sorted(str(p) for p in ports)


def _outbound_hosts(pids: List[int], seconds: float = 30.0) -> List[str]:
    """Sample /proc/<pid>/net/tcp for ESTABLISHED (01) remote IPs; passive observation."""
    seen = set()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for pid in pids:
            for path in (f"/proc/{pid}/net/tcp", f"/proc/{pid}/net/tcp6"):
                try:
                    with open(path) as fh:
                        next(fh, None)
                        for line in fh:
                            f = line.split()
                            if len(f) >= 4 and f[3] == "01":
                                seen.add(f[2].rsplit(":", 1)[0])
                except OSError:
                    pass
        time.sleep(1.0)
    return sorted(seen)


def install_size_kb(path: str) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total // 1024


def version_string(exe: str) -> str:
    try:
        return subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15).stdout.strip()[:80]
    except Exception:
        return "unknown"


def startup_ms(exe: str, argv_fn, reps: int = 5) -> float:
    """Median spawn -> CDP endpoint ready, in ms, using the adapter's argv builder."""
    from src.bench.adapters import free_port
    import urllib.request

    times = []
    for _ in range(reps):
        port = free_port()
        t0 = time.perf_counter()
        proc = subprocess.Popen(argv_fn(port, f"/tmp/inspect-{port}"),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.3).read()
                    break
                except Exception:
                    time.sleep(0.01)
            times.append((time.perf_counter() - t0) * 1000)
        finally:
            from src.bench.adapters import kill_process_tree
            kill_process_tree(proc)
    times.sort()
    return times[len(times) // 2]
