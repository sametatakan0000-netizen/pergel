"""Dayanıklı ve Kendi Kendini Onaran Altyapı Watchdog Servisi (Script-Only Cron Uyumlu)."""
import time
from typing import Any, Callable, Dict, List


class SelfHealingWatchdog:
    """Arka plan servis sağlığını denetler, çöken servisleri başlatır ve süresi dolan jetonları yeniler."""

    def __init__(
        self,
        health_probes: Dict[str, Callable[[], bool]],
        restart_fn: Callable[[str], bool],
        token_ttl_check: Callable[[], int],
        token_refresh_fn: Callable[[], bool],
        min_token_ttl_seconds: int = 300,
    ) -> None:
        self.health_probes = health_probes
        self.restart_fn = restart_fn
        self.token_ttl_check = token_ttl_check
        self.token_refresh_fn = token_refresh_fn
        self.min_token_ttl_seconds = min_token_ttl_seconds

    def run_cycle(self) -> Dict[str, Any]:
        healed_services: List[str] = []
        healthy_services: List[str] = []

        for service_name, probe in self.health_probes.items():
            is_ok = False
            try:
                is_ok = bool(probe())
            except Exception:
                is_ok = False

            if is_ok:
                healthy_services.append(service_name)
            else:
                if self.restart_fn(service_name):
                    healed_services.append(service_name)

        ttl_remaining = self.token_ttl_check()
        token_refreshed = False
        if ttl_remaining < self.min_token_ttl_seconds:
            token_refreshed = bool(self.token_refresh_fn())

        return {
            "timestamp": time.time(),
            "healthy_services": healthy_services,
            "healed_services": healed_services,
            "token_ttl_remaining": ttl_remaining,
            "token_refreshed": token_refreshed,
        }
