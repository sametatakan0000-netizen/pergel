"""AI-Native Browser Engine (SaaS) & OpenAI-Compatible Custom Provider Proxy Sunucusu."""
import asyncio
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional

from src.api.job_store import JobStore
from src.browser_engine.worker import BrowserWorker
from src.infra.self_healing_watchdog import SelfHealingWatchdog
from src.infra.webhook_dispatcher import WebhookDispatcher
from src.router.oracle_router import DynamicOracleRouter
from src.search.query_fanout import execute_fanout_and_ground


class BrowserFarmSaaSServer:
    """SaaS uçları + Hermes `provider: custom` için OpenAI-uyumlu `/v1/models` ve `/v1/chat/completions` Proxy."""

    VIRTUAL_ROUTING_PROFILES = [
        "oracle/auto",
        "oracle/eco",
        "oracle/free",
        "oracle/agentic",
        "oracle/premium",
    ]

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8090,
        db_dir: str = "/root/ai_browser_farm",
        nous_proxy_url: str = "http://127.0.0.1:8645/v1",
        driver_fn: Optional[Callable[[str, str, str], str]] = None,
        webhook_sender_fn: Optional[Callable[[str, bytes, Dict[str, str]], int]] = None,
    ) -> None:
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("Unauthenticated router must bind to loopback only")
        self.host = host
        self.db_dir = db_dir
        self.nous_proxy_url = nous_proxy_url
        os.makedirs(self.db_dir, exist_ok=True)
        self.job_store = JobStore(os.path.join(self.db_dir, "jobs.db"))
        self.router = DynamicOracleRouter(os.path.join(self.db_dir, "router.db"))
        self.worker = BrowserWorker(driver_fn=driver_fn)
        self.webhook_dispatcher = WebhookDispatcher(sender_fn=webhook_sender_fn)
        self._sessions_lock = threading.Lock()
        self.watchdog = SelfHealingWatchdog(
            health_probes={"job_store": lambda: True, "router_db": lambda: True},
            restart_fn=lambda svc: True,
            token_ttl_check=lambda: 3600,
            token_refresh_fn=lambda: True,
        )

        parent = self

        class RequestHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def _send_json(self, status: int, data: Dict[str, Any]) -> None:
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> Dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    return {}
                raw = self.rfile.read(length).decode("utf-8")
                return json.loads(raw)

            def do_GET(self) -> None:
                if self.path == "/v1/health":
                    report = parent.watchdog.run_cycle()
                    try:
                        with urllib.request.urlopen(parent.nous_proxy_url.rstrip("/") + "/models", timeout=2) as response:
                            upstream_ready = response.status == 200
                    except (urllib.error.URLError, TimeoutError, OSError):
                        upstream_ready = False
                    self._send_json(200, {
                        "status": "ok" if upstream_ready else "degraded",
                        "upstream_ready": upstream_ready, "watchdog": report,
                    })
                    return

                if self.path == "/v1/models/profiles":
                    self._send_json(200, parent.router.export_model_profiles_json())
                    return

                if self.path == "/v1/models":
                    data_rows: List[Dict[str, Any]] = [
                        {
                            "id": vp,
                            "object": "model",
                            "owned_by": "oracle-router",
                            "context_length": 1000000,
                        }
                        for vp in parent.VIRTUAL_ROUTING_PROFILES
                    ]
                    for mid, prof in parent.router.inventory.items():
                        data_rows.append(
                            {
                                "id": mid,
                                "object": "model",
                                "owned_by": prof.provider,
                                "tier": prof.tier,
                                "supports_vision": prof.supports_vision,
                                "sale_badge": prof.sale_badge,
                            }
                        )
                    self._send_json(200, {"object": "list", "data": data_rows})
                    return

                if self.path.startswith("/v1/jobs/"):
                    job_id = self.path.split("/v1/jobs/", 1)[1].strip("/")
                    try:
                        job = parent.job_store.get_job(job_id)
                        self._send_json(200, job)
                    except KeyError:
                        self._send_json(404, {"error": f"Job not found: {job_id}"})
                    return
                self._send_json(404, {"error": "Not found"})

            def do_POST(self) -> None:
                payload = self._read_json()
                if self.path == "/v1/jobs/browse":
                    url = payload.get("url", "")
                    goal = payload.get("goal", "")
                    needs_vision = bool(payload.get("needs_vision", False))
                    js_complexity = payload.get("js_complexity", "low")
                    webhook_url = payload.get("webhook_url")

                    job = parent.job_store.create_job(
                        target_url=url,
                        goal=goal,
                        needs_vision=needs_vision,
                        js_complexity=js_complexity,
                        webhook_url=webhook_url,
                    )
                    parent.job_store.mark_running(job["job_id"], engine="lightpanda")
                    exec_res = parent.worker.execute_task(
                        job_id=job["job_id"],
                        url=url,
                        needs_vision=needs_vision,
                        js_complexity=js_complexity,
                    )
                    parent.job_store.mark_completed(
                        job_id=job["job_id"],
                        engine=exec_res["final_engine"],
                        extracted_markdown=exec_res["markdown"],
                        oracle_passed=exec_res["oracle_passed"],
                    )
                    completed_job = parent.job_store.get_job(job["job_id"])
                    completed_job["discovered_apis"] = exec_res["discovered_apis"]
                    if webhook_url:
                        wh_res = parent.webhook_dispatcher.dispatch(
                            webhook_url, completed_job
                        )
                        completed_job["webhook_delivery"] = wh_res
                    self._send_json(200, completed_job)
                    return

                if self.path == "/v1/search/fanout":
                    query = payload.get("query", "")
                    res = asyncio.run(
                        execute_fanout_and_ground(
                            query,
                            search_fn=lambda sq: asyncio.sleep(
                                0,
                                result=[
                                    {
                                        "url": f"https://indexed.local/{len(sq)}",
                                        "title": sq,
                                        "snippet": f"Grounded result for {sq}",
                                    }
                                ],
                            ),
                        )
                    )
                    self._send_json(200, res)
                    return

                if self.path == "/v1/router/complete":
                    self._send_json(501, {"error": "Legacy synthetic route disabled; use /v1/chat/completions"})
                    return

                if self.path == "/v1/chat/completions":
                    if not isinstance(payload.get("messages"), list) or not payload["messages"]:
                        self._send_json(400, {"error": "messages must be a nonempty array"})
                        return
                    requested = payload.get("model", "oracle/auto")
                    if requested not in parent.VIRTUAL_ROUTING_PROFILES and requested not in parent.router.inventory:
                        self._send_json(400, {"error": "Unknown model"})
                        return
                    session_id = self.headers.get("x-hermes-session-id", "")
                    task_type, needs_vision, target_tier = parent.router.classify_chat_request(
                        payload, session_id=session_id
                    )
                    with parent._sessions_lock:
                        sticky = parent.router.session_sticky_models.get(session_id) if session_id else None
                        if requested in parent.router.inventory:
                            chosen_model = requested
                        elif sticky and requested == "oracle/auto":
                            chosen_model = sticky
                        else:
                            tier_models = parent.router.tiers[target_tier - 1]
                            candidates = [
                                m for m in tier_models if m in parent.router.inventory
                                and parent.router.inventory[m].supports_tools
                                and (not needs_vision or parent.router.inventory[m].supports_vision)
                            ]
                            if requested == "oracle/free":
                                candidates = [m for m in candidates if parent.router.inventory[m].input_cost_per_mtok == 0
                                              and parent.router.inventory[m].output_cost_per_mtok == 0]
                            if not candidates:
                                self._send_json(422, {"error": "No verified eligible model for requested profile"})
                                return
                            chosen_model = parent.router.select_best_in_tier(candidates, task_type=task_type)
                    tuning = parent.router.get_adaptive_tuning(chosen_model, task_type=task_type)
                    upstream_payload = dict(payload)
                    upstream_payload["model"] = chosen_model
                    # Preserve caller-supplied generation controls; do not forward router-only metadata.
                    upstream_payload.pop("oracle_routing", None)
                    request = urllib.request.Request(
                        parent.nous_proxy_url.rstrip("/") + "/chat/completions",
                        data=json.dumps(upstream_payload).encode("utf-8"), method="POST",
                        headers={"Content-Type": "application/json", "Authorization": "Bearer sk-local-router"},
                    )
                    response_started = False
                    try:
                        with urllib.request.urlopen(request, timeout=120) as upstream:
                            if session_id:
                                with parent._sessions_lock:
                                    parent.router.session_sticky_models[session_id] = chosen_model
                            content_type = upstream.headers.get("Content-Type", "application/json")
                            self.send_response(upstream.status)
                            self.send_header("Content-Type", content_type)
                            self.send_header("X-Oracle-Selected-Model", chosen_model)
                            self.end_headers()
                            response_started = True
                            if content_type.startswith("text/event-stream"):
                                while line := upstream.readline():
                                    self.wfile.write(line)
                                    self.wfile.flush()
                            else:
                                while chunk := upstream.read(16384):
                                    self.wfile.write(chunk)
                                    self.wfile.flush()
                    except urllib.error.HTTPError as exc:
                        body = exc.read()
                        self.send_response(exc.code)
                        self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError):
                        # The client closed a streaming response. Headers were already sent.
                        return
                    except (urllib.error.URLError, TimeoutError, OSError):
                        if not response_started:
                            self._send_json(502, {"error": "Nous subscription proxy unavailable"})
                    return

                self._send_json(404, {"error": "Unknown endpoint"})

        self._httpd = ThreadingHTTPServer((host, port), RequestHandler)
        self.port = int(self._httpd.server_address[1])
        self._thread: Optional[threading.Thread] = None

    def start_background(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=3)
