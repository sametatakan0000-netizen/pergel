"""AI-Native Browser Engine (SaaS) Birleşik REST API Sunucusu."""
import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional

from src.api.job_store import JobStore
from src.browser_engine.worker import BrowserWorker
from src.infra.self_healing_watchdog import SelfHealingWatchdog
from src.infra.webhook_dispatcher import WebhookDispatcher
from src.router.oracle_router import DynamicOracleRouter, OracleSignal
from src.search.query_fanout import execute_fanout_and_ground


class BrowserFarmSaaSServer:
    """/v1/health, /v1/jobs/browse, /v1/jobs/<id>, /v1/search/fanout ve /v1/router/complete sunucusu."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8090,
        db_dir: str = "/root/ai_browser_farm",
        driver_fn: Optional[Callable[[str, str, str], str]] = None,
        webhook_sender_fn: Optional[Callable[[str, bytes, Dict[str, str]], int]] = None,
    ) -> None:
        self.host = host
        self.db_dir = db_dir
        os.makedirs(self.db_dir, exist_ok=True)
        self.job_store = JobStore(os.path.join(self.db_dir, "jobs.db"))
        self.router = DynamicOracleRouter(os.path.join(self.db_dir, "router.db"))
        self.worker = BrowserWorker(driver_fn=driver_fn)
        self.webhook_dispatcher = WebhookDispatcher(sender_fn=webhook_sender_fn)
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
                    self._send_json(200, {"status": "ok", "watchdog": report})
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
                    prompt = payload.get("prompt", "")
                    res = parent.router.route_and_execute(
                        prompt=prompt,
                        task_type=payload.get("task_type", "general"),
                        executor=lambda model_id, p: f"[{model_id}] {p}",
                        oracle_validator=lambda out: OracleSignal(
                            passed=bool(out.strip()), channel="strong"
                        ),
                    )
                    self._send_json(200, res)
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
