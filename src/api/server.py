"""AI-Native Browser Engine (SaaS) & OpenAI-Compatible Custom Provider Proxy Sunucusu."""
import asyncio
import ipaddress
import json
import hmac
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.api.job_store import JobStore
from src.browser_engine.browser_orchestrator import BrowserFarmOrchestrator
from src.browser_engine.engine_drivers import engine_driver
from src.browser_engine.worker import BrowserWorker
from src.infra.self_healing_watchdog import SelfHealingWatchdog
from src.infra.webhook_dispatcher import WebhookDispatcher
from src.router.live_router import ADVERTISED_MODELS, VIRTUAL_PROFILES, LiveRouter, price_tier
from src.router.outcome_learning import OutcomeLearner, StreamAccumulator, analyze_response
from src.router.cost_model import cached_tokens_from
from src.router.moa_exec import build_aggregator_payload, member_usage_summary, run_members
from src.router.moa_plan import plan_moa
from src.router.moa_policy import MoaPolicy
from src.router.model_registry import fetch_profiles, load_snapshot, save_snapshot
from src.search.query_fanout import decompose_query_llm, execute_fanout_and_ground, llm_decompose_prompt

# Upstream statuses that justify trying the next candidate (capacity / availability / not on plan).
RETRYABLE_STATUSES = {404, 408, 429, 500, 502, 503, 504}

# ---- per-client rate limiting (SaaS surfaces only; router paths stay unthrottled) ----
_RATE_BUCKETS: Dict[str, list] = {}
_RATE_LOCK = threading.Lock()


def _allow_request(client_key: str) -> Tuple[bool, float]:
    """Token bucket per client; ORACLE_JOBS_RPM sets the refill rate (0 = disabled)."""
    rpm = float(os.environ.get("ORACLE_JOBS_RPM", "60") or 0)
    if rpm <= 0:
        return True, 0.0
    now = time.monotonic()
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS.get(client_key)
        if bucket is None:
            bucket = _RATE_BUCKETS[client_key] = [float(rpm), now]
        bucket[0] = min(rpm, bucket[0] + (now - bucket[1]) * rpm / 60.0)
        bucket[1] = now
        if bucket[0] >= 1.0:
            bucket[0] -= 1.0
            return True, 0.0
        return False, (1.0 - bucket[0]) * 60.0 / rpm


_RATE_LIMITED_PREFIXES = ("/v1/jobs/",)
_RATE_LIMITED_PATHS = {"/v1/jobs/browse", "/v1/search/fanout"}
# Amiral + subagent turns are governed per bucket by MoaPolicy (evidence from implicit
# feedback). Opt-in (ORACLE_MOA=1): each member re-reads the whole 100K+ context, so N members
# multiply the dominant cost, and moa_policy.db holds no evidence MoA beat a single model.
MOA_ENABLED = os.environ.get("ORACLE_MOA", "0") == "1"


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _usage_from(raw: bytes) -> Dict[str, Any]:
    try:
        usage = json.loads(raw).get("usage")
    except (ValueError, AttributeError):
        return {}
    return usage if isinstance(usage, dict) else {}


def _validate_target(url: Any, allow_private: bool) -> Optional[str]:
    """Reject non-http(s) and loopback/private/link-local targets (SSRF guard). Returns error text or None."""
    if not isinstance(url, str) or not url:
        return "url is required"
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "url must be http(s) with a host"
    if allow_private:
        return None
    try:
        infos = socket.getaddrinfo(parts.hostname, None)
    except socket.gaierror:
        return None  # shortcut: unresolvable host passes (fetch fails itself); DNS-rebinding/redirect-to-private not covered, pin resolved IP when exposed publicly
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return "target resolves to a private/loopback address"
    return None


class BrowserFarmSaaSServer:
    """SaaS uçları + Hermes `provider: custom` için OpenAI-uyumlu `/v1/models` ve `/v1/chat/completions` Proxy."""

    VIRTUAL_ROUTING_PROFILES = list(VIRTUAL_PROFILES)
    MAX_ATTEMPTS = 3
    UPSTREAM_TIMEOUT = 600

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8090,
        db_dir: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        nous_proxy_url: str = "http://127.0.0.1:8645/v1",
        driver_fn: Optional[Callable[[str, str, str], str]] = None,
        webhook_sender_fn: Optional[Callable[[str, bytes, Dict[str, str]], int]] = None,
        profiles: Optional[Dict[str, Any]] = None,
        registry_path: Optional[str] = None,
        explore_epsilon: Optional[float] = None,
        search_fn: Optional[Callable[[str], Any]] = None,
        allow_private_targets: bool = False,
    ) -> None:
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("Unauthenticated router must bind to loopback only")
        self.host = host
        self.search_fn = search_fn  # None -> SearXNG default (ORACLE_SEARXNG_URL)
        self.allow_private_targets = allow_private_targets
        self.db_dir = db_dir
        self.nous_proxy_url = nous_proxy_url
        os.makedirs(self.db_dir, exist_ok=True)
        self.job_store = JobStore(os.path.join(self.db_dir, "jobs.db"))
        self.registry_path = registry_path or os.path.join(self.db_dir, "model_registry.json")
        self.registry_fetched_at: Optional[str] = None
        if profiles is None and os.path.exists(self.registry_path):
            profiles, self.registry_fetched_at = load_snapshot(self.registry_path)
        epsilon = float(os.environ.get("ORACLE_EXPLORE_EPSILON", "0.05")) if explore_epsilon is None else explore_epsilon
        self.live = LiveRouter(os.path.join(self.db_dir, "live_router.db"), profiles or {},
                               explore_epsilon=epsilon)
        self.moa_policy = MoaPolicy(os.path.join(self.db_dir, "moa_policy.db"))
        # The loopback Hermes subscription proxy holds the real Portal credentials.
        self.upstream_api_key = os.environ.get("ORACLE_UPSTREAM_API_KEY", "local-router")
        self.worker = BrowserWorker(
            driver_fn=driver_fn or engine_driver,
            orchestrator=BrowserFarmOrchestrator(db_path=os.path.join(self.db_dir, "browser_memory.db")),
        )
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

            def _send_json(self, status: int, data: Dict[str, Any],
                           extra_headers: Optional[Dict[str, str]] = None) -> None:
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                for name, value in (extra_headers or {}).items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> Dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    return {}
                raw = self.rfile.read(length).decode("utf-8")
                return json.loads(raw)

            def _jobs_authorized(self) -> bool:
                """/v1/jobs/* needs BROWSE_API_KEY when it is set (empty = auth disabled, loopback only)."""
                if not self.path.startswith("/v1/jobs/"):
                    return True
                key = os.environ.get("BROWSE_API_KEY", "")
                if not key:
                    return True
                header = self.headers.get("Authorization", "")
                return hmac.compare_digest(header, f"Bearer {key}")

            def _throttled(self) -> bool:
                limited = (self.path.startswith(_RATE_LIMITED_PREFIXES)
                           or self.path in _RATE_LIMITED_PATHS)
                if not limited:
                    return False
                ok, retry_after = _allow_request(self.client_address[0])
                if ok:
                    return False
                self._send_json(429, {"error": "rate limit exceeded"},
                                extra_headers={"Retry-After": str(max(1, int(retry_after + 0.5)))})
                return True

            def do_GET(self) -> None:
                if not self._jobs_authorized():
                    self._send_json(401, {"error": "Unauthorized"})
                    return
                if self._throttled():
                    return
                if self.path == "/v1/health":
                    report = parent.watchdog.run_cycle()
                    try:
                        with urllib.request.urlopen(parent.nous_proxy_url.rstrip("/") + "/models", timeout=2) as response:
                            upstream_ready = response.status == 200
                    except (urllib.error.URLError, TimeoutError, OSError):
                        upstream_ready = False
                    routable = sum(p.routable for p in parent.live.profiles.values())
                    self._send_json(200, {
                        "status": "ok" if upstream_ready and routable else "degraded",
                        "upstream_ready": upstream_ready,
                        "registry": {"fetched_at": parent.registry_fetched_at, "routable": routable},
                        "watchdog": report,
                    })
                    return

                if self.path == "/v1/router/learning":
                    self._send_json(200, parent.live.learner.summary())
                    return

                if self.path == "/v1/models/profiles":
                    profiles = parent.live.profiles
                    self._send_json(200, {
                        "fetched_at": parent.registry_fetched_at,
                        "total_models": len(profiles),
                        "routable": sum(p.routable for p in profiles.values()),
                        "profiles": {mid: asdict(p) for mid, p in sorted(profiles.items())},
                    })
                    return

                if self.path == "/v1/models":
                    # One entry only: tier profiles are meaningless now that plan() picks the
                    # band itself (Pareto + tolerance + sticky). Raw registry models and the old
                    # virtual aliases (oracle/eco|agentic|premium|free) stay routable by explicit
                    # id and inspectable at /v1/models/profiles — advertising them was noise and a
                    # misclick bypassed routing policy.
                    # Largest window: plan() skips candidates a request outgrows, so Hermes does
                    # not have to compress down to the smallest model's window.
                    rows: List[Dict[str, Any]] = [
                        {"id": vp, "object": "model", "owned_by": "oracle-router",
                         "context_length": parent.live.virtual_context_length(vp)}
                        for vp in ADVERTISED_MODELS
                    ]
                    self._send_json(200, {"object": "list", "data": rows})
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
                if not self._jobs_authorized():
                    self._send_json(401, {"error": "Unauthorized"})
                    return
                if self._throttled():
                    return
                payload = self._read_json()
                if self.path == "/v1/jobs/browse":
                    url = payload.get("url", "")
                    goal = payload.get("goal", "")
                    needs_vision = bool(payload.get("needs_vision", False))
                    js_complexity = payload.get("js_complexity", "low")
                    webhook_url = payload.get("webhook_url")
                    err = _validate_target(url, parent.allow_private_targets)
                    if err:
                        self._send_json(400, {"error": err})
                        return

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
                    completed_job["attempted_engines"] = exec_res["attempted_engines"]
                    completed_job["blocked"] = bool(exec_res.get("blocked"))
                    if webhook_url:
                        wh_res = parent.webhook_dispatcher.dispatch(
                            webhook_url, completed_job
                        )
                        completed_job["webhook_delivery"] = wh_res
                    self._send_json(200, completed_job)
                    return

                if self.path == "/v1/search/fanout":
                    query = str(payload.get("query", "")).strip()
                    if not query:
                        self._send_json(400, {"error": "query must be a non-empty string"})
                        return
                    try:
                        res = asyncio.run(execute_fanout_and_ground(query, search_fn=parent.search_fn,
                                                            decompose_fn=parent._fanout_decompose_fn()))
                    except Exception as exc:  # never fabricate sources when the index is unreachable
                        self._send_json(502, {"error": f"search backend unavailable: {type(exc).__name__}"})
                        return
                    self._send_json(200, res)
                    return

                if self.path == "/v1/router/moa":
                    # Decision preview only: nothing is sent upstream, no tokens are spent.
                    if not isinstance(payload.get("messages"), list) or not payload["messages"]:
                        self._send_json(400, {"error": "messages must be a nonempty array"})
                        return
                    payload["model"] = parent.live.normalize_model(payload.get("model"))
                    session_id = self.headers.get("x-hermes-session-id", "") or None
                    try:
                        # Spend comes from our own recorded usage, not from the caller: a
                        # client-supplied number would sit at 0 forever and the shrinkage
                        # would never fire. An explicit value may only raise it.
                        spent = max(parent.live.spent_today(), float(payload.get("spent_today_usd") or 0.0))
                        decision = plan_moa(parent.live, payload, session_id=session_id,
                                            spent_today_usd=spent,
                                            force=bool(payload.get("force", False)))
                        decision["moa"]["spent_today_usd"] = round(spent, 4)
                    except KeyError as exc:
                        self._send_json(404, {"error": f"Unknown model: {exc.args[0]}"})
                        return
                    self._send_json(200, decision)
                    return

                if self.path == "/v1/router/complete":
                    self._send_json(501, {"error": "Legacy synthetic route disabled; use /v1/chat/completions"})
                    return

                if self.path == "/v1/chat/completions":
                    if not isinstance(payload.get("messages"), list) or not payload["messages"]:
                        self._send_json(400, {"error": "messages must be a nonempty array"})
                        return
                    session_id = self.headers.get("x-hermes-session-id", "") or None
                    payload["model"] = parent.live.normalize_model(payload.get("model"))
                    routed = payload["model"] in VIRTUAL_PROFILES
                    if routed:
                        signal = parent.live.learner.on_request(session_id, payload)
                        parent.moa_policy.settle(session_id, signal)  # attribute to the arm used
                        if signal == "user_retry":
                            parent.live.clear_sticky(session_id)  # regenerate = dissatisfied: re-pick
                    try:
                        plan, bucket, _ = parent.live.plan_with_context(payload, session_id=session_id)
                    except KeyError:
                        self._send_json(400, {"error": "Unknown model"})
                        return
                    if not plan:
                        self._send_json(422, {"error": "No verified eligible model for requested profile"})
                        return
                    if routed and MOA_ENABLED:
                        payload, plan, _moa = parent._apply_moa(payload, plan, session_id, bucket)
                    parent._forward_chat(self, payload, plan[: parent.MAX_ATTEMPTS], session_id, bucket, routed)
                    return

                self._send_json(404, {"error": "Unknown endpoint"})

        self._httpd = ThreadingHTTPServer((host, port), RequestHandler)
        self.port = int(self._httpd.server_address[1])
        self._thread: Optional[threading.Thread] = None

    def refresh_registry(self) -> int:
        """Re-read public catalog + metadata (no inference). Returns routable model count."""
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        profiles = fetch_profiles(fetched_at)
        save_snapshot(self.registry_path, profiles, fetched_at)
        self.live.update_profiles(profiles)
        self.registry_fetched_at = fetched_at
        return sum(p.routable for p in profiles.values())

    def _fanout_decompose_fn(self):
        """Opt-in semantic query decomposition (ORACLE_FANOUT_LLM=1): one tiny call to the
        cheapest served priced model per fan-out. Default off — no hidden model calls.
        Any failure falls back to lexical decomposition inside decompose_query_llm."""
        if os.environ.get("ORACLE_FANOUT_LLM", "0") != "1":
            return None

        def _decompose(query: str):
            served = self.live.served_models()
            priced = [(mid, (p.billed_cost_in or 0.0) + (p.billed_cost_out or 0.0))
                      for mid, p in self.live.profiles.items()
                      if mid in served and p.billed_cost_in is not None]
            if not priced:
                return None
            model_id = min(priced, key=lambda t: t[1])[0]

            def _call(prompt: str) -> str:
                status, body = self._call_upstream(model_id, {
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                })
                if status != 200:
                    raise RuntimeError(f"decompose call failed: HTTP {status}")
                choices = body.get("choices") or []
                return ((choices[0].get("message") or {}).get("content") or "")

            return decompose_query_llm(query, _call)

        return _decompose

    def _call_upstream(self, model_id: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Non-streaming call for a subagent. Usage is recorded (spend accounting) but the
        outcome is not fed to the learner: members are internal drafts, not user feedback."""
        upstream_payload = self.live.prepare_payload(payload, model_id)
        upstream_payload.pop("oracle_routing", None)
        request = urllib.request.Request(
            self.nous_proxy_url.rstrip("/") + "/chat/completions",
            data=json.dumps(upstream_payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.upstream_api_key}"},
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.UPSTREAM_TIMEOUT) as upstream:
                status, raw = upstream.status, upstream.read()
        except urllib.error.HTTPError as exc:
            self.live.record_upstream(model_id, exc.code, _elapsed_ms(started))
            return exc.code, {}
        except (urllib.error.URLError, TimeoutError, OSError):
            return 502, {}
        try:
            body = json.loads(raw)
        except ValueError:
            body = {}
        usage = body.get("usage") if isinstance(body, dict) and isinstance(body.get("usage"), dict) else {}
        self.live.record_upstream(model_id, status, _elapsed_ms(started),
                                  usage.get("prompt_tokens"), usage.get("completion_tokens"),
                                  cached_tokens=cached_tokens_from(usage))
        return status, body if isinstance(body, dict) else {}

    def _apply_moa(self, payload: Dict[str, Any], plan: List[str], session_id: Optional[str],
                   bucket: str) -> Tuple[Dict[str, Any], List[str], Dict[str, Any]]:
        """Amiral + subagents, chosen per bucket by MoaPolicy. Returns the (possibly enriched)
        payload, the unchanged plan (plan[0] stays the Amiral) and a decision summary.
        Only turns where MoA is physically possible (members fit the cap) enter the arm
        comparison; any failure degrades to the plain single-model path."""
        try:
            decision = plan_moa(self.live, payload, session_id=session_id,
                                spent_today_usd=self.live.spent_today())
        except Exception:
            return payload, plan, {"enabled": False, "reason": "decision error"}
        members = decision["moa"]["members"] if decision["moa"]["enabled"] else []
        if not members or decision["amiral"] != plan[0]:
            return payload, plan, {"enabled": False, "reason": decision["moa"]["reason"]}
        mode = self.moa_policy.choose(bucket)
        if session_id:
            self.moa_policy.remember(session_id, bucket, mode)  # feedback arrives next turn
        if mode == "single":
            return payload, plan, {"enabled": False, "reason": "policy: single arm",
                                   "bucket": bucket, "amiral": plan[0]}
        drafts = run_members(self._call_upstream, members, payload)
        info = member_usage_summary(drafts, members)
        info.update({"enabled": bool(drafts), "amiral": plan[0], "bucket": bucket,
                     "cap_usd": decision["moa"]["cap_usd"]})
        if not drafts:
            return payload, plan, info
        return build_aggregator_payload(payload, drafts), plan, info

    def _forward_chat(self, handler: BaseHTTPRequestHandler, payload: Dict[str, Any], plan: List[str],
                      session_id: Optional[str], bucket: str, routed: bool) -> None:
        last_error = None
        messages = payload.get("messages") or []
        user_hash = OutcomeLearner.last_user_hash(messages)
        tools = payload.get("tools")

        def learn(model_id: str, ok: bool, final: bool, reason: str) -> None:
            profile = self.live.profiles.get(model_id)
            tier = price_tier(profile) if profile else 0
            # Explicit-model calls (e.g. Hermes aux titles sharing the session id) only feed
            # structural evidence; implicit user feedback is tracked for router decisions only.
            self.live.learner.on_response(session_id if routed else None, model_id, bucket, tier,
                                          structural_ok=ok, final_answer=final, last_user_hash=user_hash,
                                          msg_count=len(messages), reason=reason)

        for index, model_id in enumerate(plan):
            upstream_payload = self.live.prepare_payload(payload, model_id)
            upstream_payload.pop("oracle_routing", None)
            request = urllib.request.Request(
                self.nous_proxy_url.rstrip("/") + "/chat/completions",
                data=json.dumps(upstream_payload).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.upstream_api_key}"},
            )
            started = time.monotonic()
            try:
                upstream = urllib.request.urlopen(request, timeout=self.UPSTREAM_TIMEOUT)
            except urllib.error.HTTPError as exc:
                body = exc.read()
                self.live.record_upstream(model_id, exc.code, _elapsed_ms(started))
                last_error = (exc.code, exc.headers.get("Content-Type", "application/json"), body, model_id)
                if exc.code in RETRYABLE_STATUSES:
                    continue
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                # Proxy-level failure, not the model's fault: no cooldown, no fallback.
                timed_out = isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)
                handler._send_json(504 if timed_out else 502, {
                    "error": "Nous subscription proxy timed out" if timed_out else "Nous subscription proxy unavailable"
                })
                return

            with upstream:
                content_type = upstream.headers.get("Content-Type", "application/json")
                if content_type.startswith("text/event-stream"):
                    self._relay_stream(handler, upstream, model_id, session_id, started, routed, tools, learn)
                    return
                body = upstream.read()
                status = upstream.status
            try:
                parsed = json.loads(body)
            except ValueError:
                parsed = None
            ok, final, reason = analyze_response(parsed, tools) if isinstance(parsed, dict) else (False, False, "unparseable")
            usage = parsed.get("usage") if isinstance(parsed, dict) and isinstance(parsed.get("usage"), dict) else {}
            self.live.record_upstream(model_id, status, _elapsed_ms(started),
                                      usage.get("prompt_tokens"), usage.get("completion_tokens"),
                                      cached_tokens=cached_tokens_from(usage))
            learn(model_id, ok, final, reason)
            if not ok and index < len(plan) - 1:
                # Self-healing: a broken non-stream answer never reaches the client if another
                # candidate exists. Costs an extra call only when the first one was unusable.
                last_error = (status, content_type, body, model_id)
                continue
            if routed:
                self.live.commit_choice(session_id, model_id)
            handler.send_response(status)
            handler.send_header("Content-Type", content_type)
            handler.send_header("X-Oracle-Selected-Model", model_id)
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            try:
                handler.wfile.write(body)
            except OSError:
                pass
            return

        status, content_type, body, model_id = last_error
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("X-Oracle-Selected-Model", model_id)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _relay_stream(self, handler: BaseHTTPRequestHandler, upstream: Any, model_id: str,
                      session_id: Optional[str], started: float, routed: bool,
                      tools: Optional[List[Dict[str, Any]]], learn: Callable[[str, bool, bool, str], None]) -> None:
        if routed:
            # Only router decisions define session affinity. Explicit-model calls that share the
            # session id (Hermes titles/compression) must not overwrite the conversation's model.
            self.live.commit_choice(session_id, model_id)
        handler.send_response(upstream.status)
        handler.send_header("Content-Type", upstream.headers.get("Content-Type", "text/event-stream"))
        handler.send_header("X-Oracle-Selected-Model", model_id)
        handler.end_headers()
        accumulator = StreamAccumulator()
        usage: Dict[str, Any] = {}
        try:
            while line := upstream.readline():
                handler.wfile.write(line)
                handler.wfile.flush()
                accumulator.feed(line)
                if line.startswith(b"data: {") and b'"usage"' in line:
                    usage = _usage_from(line[6:]) or usage
        except OSError:
            pass  # client or upstream closed mid-stream; headers are already sent
        self.live.record_upstream(model_id, upstream.status, _elapsed_ms(started),
                                  usage.get("prompt_tokens"), usage.get("completion_tokens"),
                                  cached_tokens=cached_tokens_from(usage))
        ok, final, reason = analyze_response(accumulator.as_response(), tools)
        learn(model_id, ok, final, reason)

    def start_background(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=3)
