"""Linux Oyun (Sober / Minecraft) Ağ Soket ve MTU/TLS Tanılama Modülü."""
import re
from typing import Any, Dict, List


def analyze_socket_trace_and_recommend_routing(trace_text: str) -> Dict[str, Any]:
    """`strace` ağ soket çıktılarını analiz ederek bağlantı sıfırlama ve zaman aşımı kanıtlarını raporlar."""
    ips = sorted(set(re.findall(r'inet_addr\("([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)"\)', trace_text)))
    has_timeout = "ETIMEDOUT" in trace_text
    has_reset = "ECONNRESET" in trace_text

    if has_timeout or has_reset:
        issue = "TLS_HANDSHAKE_RESET_OR_TIMEOUT"
        recommended_mtu = 1400
    else:
        issue = "HEALTHY"
        recommended_mtu = 1500

    return {
        "detected_issue": issue,
        "affected_ips": ips,
        "recommended_mtu": recommended_mtu,
        "evidence_tagged": True,
        "diagnostic_summary": (
            f"Detected {issue} across {len(ips)} endpoint(s); recommended interface MTU={recommended_mtu}."
        ),
    }
