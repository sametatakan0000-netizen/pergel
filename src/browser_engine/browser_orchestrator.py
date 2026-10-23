"""Çoklu Motorlu Self-Evolving Tarayıcı Orkestratörü (Lightpanda, Chromium Browser-Use, Camofox)."""
import urllib.parse
from typing import Any, Dict, List, Optional

from src.devtools.self_evolution_engine import distill_evolution_record


class BrowserFarmOrchestrator:
    """Görev gereksinimine ve öğrenilmiş domain geçmişine göre tarayıcı motoru seçer, izole session üretir."""

    ENGINE_RANK = {
        "lightpanda": 0,
        "chromium-browser-use": 1,
        "camofox": 2,
    }

    def __init__(self) -> None:
        self.domain_engine_floors: Dict[str, str] = {}
        self.domain_discovered_apis: Dict[str, List[str]] = {}
        self.evolution_ledger: List[Dict[str, str]] = []

    @staticmethod
    def _extract_domain(url: str) -> str:
        if not url:
            return ""
        parsed = urllib.parse.urlparse(url)
        return (parsed.hostname or "").lower()

    def select_engine(
        self,
        needs_vision: bool = False,
        js_complexity: str = "low",
        url: str = "",
    ) -> str:
        if not needs_vision and js_complexity == "low":
            base_engine = "lightpanda"
        elif js_complexity == "isolated_profile":
            base_engine = "camofox"
        else:
            base_engine = "chromium-browser-use"

        domain = self._extract_domain(url)
        learned_floor = self.domain_engine_floors.get(domain)
        if learned_floor and self.ENGINE_RANK.get(learned_floor, 0) > self.ENGINE_RANK.get(base_engine, 0):
            return learned_floor
        return base_engine

    def record_domain_escalation(
        self,
        url: str,
        attempted_engines: List[str],
        final_engine: str,
        discovered_apis: Optional[List[str]] = None,
    ) -> None:
        """Alt motorların başarısız olduğu domainlerde motor tabanını ve keşfedilen HAR API uçlarını evrimleştirir."""
        domain = self._extract_domain(url)
        if not domain:
            return

        current_floor = self.domain_engine_floors.get(domain, "lightpanda")
        if (
            len(attempted_engines) > 1
            and self.ENGINE_RANK.get(final_engine, 0) > self.ENGINE_RANK.get(current_floor, 0)
        ):
            self.domain_engine_floors[domain] = final_engine
            self.evolution_ledger.append(
                distill_evolution_record(
                    mode="FIX",
                    source=f"BrowserFarmOrchestrator:{domain}",
                    decision=f"Promote default browser engine floor for '{domain}' from {attempted_engines[0]} to {final_engine}",
                    evidence=f"Attempted={attempted_engines} -> Oracle passed on {final_engine}",
                )
            )

        if discovered_apis:
            existing = self.domain_discovered_apis.setdefault(domain, [])
            new_apis = [api for api in discovered_apis if api not in existing]
            if new_apis:
                existing.extend(new_apis)
                self.evolution_ledger.append(
                    distill_evolution_record(
                        mode="CAPTURED",
                        source=f"HAR-Discovery:{domain}",
                        decision=f"Cache {len(new_apis)} direct XHR/JSON endpoints for '{domain}'",
                        evidence=", ".join(new_apis[:3]),
                    )
                )

    def build_session_task(
        self,
        job_id: str,
        url: str,
        needs_vision: bool = False,
        js_complexity: str = "low",
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        clean_id = job_id.strip().replace(" ", "_")
        engine = self.select_engine(
            needs_vision=needs_vision, js_complexity=js_complexity, url=url
        )
        return {
            "job_id": clean_id,
            "session_name": f"farm_{clean_id}",
            "target_url": url,
            "engine": engine,
            "needs_vision": needs_vision,
            "webhook_url": webhook_url,
            "timeout_seconds": 60,
        }
