"""3 Modlu (FIX / DERIVED / CAPTURED) Self-Evolution ve Claude Duet Sessiz Watchdog Motoru."""
import hashlib
import json
from typing import Any, Dict, List


def evaluate_silent_watchdog(
    disk_free_gb: float,
    failed_tests: int,
    unhealthy_services: List[str],
    min_disk_gb: float = 5.0,
) -> str:
    """'İyi ajan az konuşur': Sistem tamamen sağlıklıysa boş string ('') döner (0 bildirim)."""
    anomalies: List[str] = []
    if disk_free_gb < min_disk_gb:
        anomalies.append(f"LOW_DISK: {disk_free_gb:.1f}GB free (<{min_disk_gb}GB)")
    if failed_tests > 0:
        anomalies.append(f"FAILED_TESTS: {failed_tests}")
    if unhealthy_services:
        anomalies.append(f"UNHEALTHY_SERVICES: {', '.join(unhealthy_services)}")

    if not anomalies:
        return ""
    return "ANOMALY_DETECTED | " + " | ".join(anomalies)


def compute_ecosystem_fingerprint(state: Dict[str, Any]) -> str:
    """Zaman damgasız deterministik SHA-256 parmak izi üretir (Hermes cron `monitor` kapısı için)."""
    canonical = json.dumps(state, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def distill_evolution_record(
    mode: str,
    source: str,
    decision: str,
    evidence: str,
) -> Dict[str, str]:
    """Rate-Distortion Memory ('Remember the Decision, Not the Description') formatında evrim kaydı."""
    normalized_mode = mode.strip().upper()
    if normalized_mode not in {"FIX", "DERIVED", "CAPTURED"}:
        raise ValueError(f"Invalid evolution mode: {mode}")

    compact_entry = f"[{normalized_mode}] ({source}) Decision: {decision} | Receipt: {evidence}"
    return {
        "mode": normalized_mode,
        "source": source,
        "decision": decision,
        "evidence": evidence,
        "compact_entry": compact_entry,
    }
