"""Idle network posture probe: which remote hosts does a freshly started, blank-profile browser contact?

Passive only: we read ESTABLISHED sockets of the browser's own process tree from /proc and
resolve nothing on the wire. No traffic is injected, no TLS is intercepted, no other
process is touched. The browser runs headless with a throw-away profile.
"""
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
from typing import Dict, List, Set

from src.bench.adapters import chromium_argv, free_port, kill_process_tree
from src.bench.procmem import tree_pids

TCP_STATES = {"01": "ESTABLISHED", "02": "SYN_SENT", "06": "TIME_WAIT"}


def _hex_to_ip(hexaddr: str) -> str:
    if len(hexaddr) == 8:  # IPv4, little-endian
        return socket.inet_ntoa(struct.pack("<I", int(hexaddr, 16)))
    raw = bytes.fromhex(hexaddr)  # IPv6: four little-endian 32-bit words
    words = [raw[i:i + 4][::-1] for i in range(0, 16, 4)]
    return socket.inet_ntop(socket.AF_INET6, b"".join(words))


def parse_proc_net_tcp(text: str, states=("01", "02")) -> Set[str]:
    """Remote ip:port of sockets in the given states, loopback excluded."""
    out: Set[str] = set()
    for line in text.splitlines()[1:]:
        f = line.split()
        if len(f) < 4 or f[3] not in states:
            continue
        rem_ip, rem_port = f[2].split(":")
        ip = _hex_to_ip(rem_ip)
        if ip.startswith("127.") or ip in ("::1", "0.0.0.0", "::"):
            continue
        out.add(f"{ip}:{int(rem_port, 16)}")
    return out


def reverse_dns(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except OSError:
        return ""


def probe_idle(exe: str, seconds: float = 60.0) -> Dict:
    """Start the browser blank, sample its tree for ``seconds``, return remote endpoints seen."""
    port, prof = free_port(), tempfile.mkdtemp(prefix="net-probe-")
    proc = subprocess.Popen(chromium_argv(exe, port, prof), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    seen: Set[str] = set()
    try:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for pid in tree_pids(proc.pid):
                for path in (f"/proc/{pid}/net/tcp", f"/proc/{pid}/net/tcp6"):
                    try:
                        seen |= parse_proc_net_tcp(open(path).read())
                    except OSError:
                        pass
            time.sleep(0.5)
    finally:
        kill_process_tree(proc)
        shutil.rmtree(prof, ignore_errors=True)
    hosts = {}
    for ep in sorted(seen):
        ip = ep.rsplit(":", 1)[0]
        hosts[ep] = reverse_dns(ip)
    return {"exe": exe, "seconds": seconds, "endpoints": hosts}
