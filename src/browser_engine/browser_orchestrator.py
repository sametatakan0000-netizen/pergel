"""Çoklu Motorlu Otonom Tarayıcı Orkestratörü (Lightpanda, Chromium Browser-Use, Camofox)."""
from typing import Any, Dict, Optional


class BrowserFarmOrchestrator:
    """Görev gereksinimine göre tarayıcı motoru seçer, izole session üretir ve Webhook tanımlar."""

    def select_engine(self, needs_vision: bool = False, js_complexity: str = "low") -> str:
        if not needs_vision and js_complexity == "low":
            return "lightpanda"
        if js_complexity == "isolated_profile":
            return "camofox"
        return "chromium-browser-use"

    def build_session_task(
        self,
        job_id: str,
        url: str,
        needs_vision: bool = False,
        js_complexity: str = "low",
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        clean_id = job_id.strip().replace(" ", "_")
        engine = self.select_engine(needs_vision=needs_vision, js_complexity=js_complexity)
        return {
            "job_id": clean_id,
            "session_name": f"farm_{clean_id}",
            "target_url": url,
            "engine": engine,
            "needs_vision": needs_vision,
            "webhook_url": webhook_url,
            "timeout_seconds": 60,
        }
