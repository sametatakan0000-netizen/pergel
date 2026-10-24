"""Hands-on inspection cards: one markdown file per browser target.

The card is a research artifact, not a benchmark: it records what we OBSERVED (version,
process model, automation surface, idle network) plus what public docs say, and it never
invents a score. Every card carries its sources and, if the target could not be run on
this host, the explicit label 'desk research — not run on this host'.
"""
from typing import Dict, List, Optional


def format_card(target_id: str, family: str, info: Dict, sources: List[str],
                desk_research: bool = False) -> str:
    if not sources:
        raise ValueError("every card must cite at least one source")
    if desk_research:
        status = "Status: **desk research — not run on this host**"
    else:
        status = "Status: measured on this host"
    lines = [
        f"# {target_id}",
        "",
        status,
        f"Engine / family: {family}",
        f"Version: {info.get('version', 'unknown')}",
        f"Install size: {info.get('install_size_kb', 'n/a')} KB",
        f"Startup (spawn -> CDP ready): {info.get('startup_ms', 'n/a')} ms (median)",
        f"Idle PSS (0 tabs): {info.get('idle_pss_kib', 'n/a')} KiB",
        f"Processes at idle: {info.get('pids', 'n/a')}",
        f"Automation surface: {', '.join(info.get('protocols', ['unknown']))}",
        f"Listening ports at idle: {', '.join(info.get('listening_ports', ['none'])) or 'none'}",
        f"Outbound hosts contacted at idle: {', '.join(info.get('outbound_hosts', ['none'])) or 'none'}",
        "",
        "Sources:",
    ]
    lines += [f"- {s}" for s in sources]
    return "\n".join(lines)


def pick_stack(rows: List[Dict]) -> List[Dict]:
    """Sort inspection targets: lightpanda first, then by family, then id (stable report order)."""
    order = {"lightpanda": 0, "chromium": 1, "gecko": 2, "webkit": 3}
    return sorted(rows, key=lambda r: (order.get(r.get("family", ""), 9), r["id"]))


def collect_live_info(target_id: str, exe: str) -> Dict:
    """Measure the fields we can observe without any network MITM: version, install size,
    startup latency, idle PSS, process count, listening ports, and (passively, 30 s) any
    outbound hosts. A target that fails to launch returns {"blocked": reason}."""
    # shortcut: outbound host capture is /proc/<pid>/net/tcp sampling only (no MITM, no injection).
    raise NotImplementedError("filled in per-target during the live inspection run")
