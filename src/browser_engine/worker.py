"""Kademeli Motor Yükseltmeli (Engine Cascading) Tarayıcı İşçisi ve HAR/XHR API Keşfedici."""
import html
import re
import time
import urllib.error
import urllib.parse
import urllib.robotparser
import urllib.request
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Dict, List, Optional
from src.browser_engine.browser_orchestrator import BrowserFarmOrchestrator
from src.browser_engine.platform_adapters import (
    AdapterResult,
    AdapterRegistry,
    default_registry,
)
from src.browser_engine.egress_proxy import (
    EgressAddressError,
    EgressDenied,
    EgressPolicy,
    pinned_opener,
)


def _strip_non_script_tags(raw_html: str) -> str:
    """Drop <link>/<meta> tags (icons, manifests, canonical) that are not API calls."""
    return re.sub(r"<(?:link|meta)\b[^>]*>", "", raw_html, flags=re.IGNORECASE)


def discover_har_api_endpoints(raw_html: str, base_url: str = "") -> List[str]:
    """`har-derived-api-client` desenine uygun olarak sayfa kaynağındaki XHR/JSON API uçlarını keşfeder."""
    # shortcut: regex, not a DOM/JS parser; only quoted strings inside JS network calls
    # or script blocks count, so <link> icons/manifests are not reported as APIs.
    pattern = re.compile(
        r"""(?:fetch|axios\.(?:get|post)|XMLHttpRequest|["'])((?:https?://|/)[^"'\s)<>]*?(?:api|graphql|\.json)[^"'\s)<>]*)["']""",
        re.IGNORECASE,
    )
    found: List[str] = []
    for match in pattern.finditer(_strip_non_script_tags(raw_html)):
        candidate = re.sub(r"(\\[nrt])+$", "", match.group(1).strip()).rstrip("\\")
        if base_url and candidate.startswith("/"):
            candidate = urllib.parse.urljoin(base_url, candidate)
        if candidate not in found:
            found.append(candidate)
    return found


try:
    import trafilatura
except ImportError:  # shortcut: regex fallback drops only nav/header/footer/aside landmarks, trafilatura preferred in production deploys
    trafilatura = None

_MIN_EXTRACTED_CHARS = 80  # shorter results are usually fragments/SPA shells; regex path keeps them

MIN_ACCEPT_CHARS = 10  # minimum markdown to accept a page as done (else escalate)

# JS-app shell signals: the page's real content is client-rendered, so a thin
# static extraction is a shell, not a finished page. Presence + thin extraction
# forces escalation to a JS-capable engine instead of accepting the shell.
_JS_APP_MARKERS = (
    'data-reactroot', "__NEXT_DATA__", 'id="root"', "id='root'",
    'ng-app', 'ng-controller', 'data-v-', 'id="__nuxt"',
    "ReactDOM.render", "createRoot", "window.__INITIAL_STATE__",
    "Vue(", "angular.module", "data-reactid",
)


def looks_like_js_app_shell(raw_html: str, extracted_md: str) -> bool:
    """True when the raw HTML is a client-rendered app whose extracted text is thin.

    A thin-but-nonempty extraction (chrome: promo paragraphs, category lists)
    must not be accepted as a finished page when the real content is JS-only.
    Thin is relative to the HTML's payload: SPA shells ship large script/markup
    bundles with little extractable text (GitLab: 433KB -> 38 words), while real
    content pages carry text proportional to their HTML (Wikipedia: 236KB -> 41KB).
    """
    if not raw_html:
        return False
    # Strip script/style BODIES before marker scanning: browser engines
    # instrument pages with their own injected bundles (cookie-banner
    # selectors, adblock lists) that mention framework attribute strings
    # like `ng-app` in CSS selector source, not as real DOM markers.
    body = re.sub(r"<script[^>]*>.*?</script>", "", raw_html,
                  flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<script[^>]*/>", "", body, flags=re.IGNORECASE)
    body = re.sub(r"<style[^>]*>.*?</style>", "", body,
                  flags=re.DOTALL | re.IGNORECASE)
    body = body.lower()
    if not any(m.lower() in body for m in _JS_APP_MARKERS):
        return False
    md_len = len(extracted_md.strip())
    # Absolute thin: almost no extractable text at all.
    if md_len < MIN_ACCEPT_CHARS:
        return True
    # Relative thin: a large client-rendered payload with little text to show for
    # it. Only large HTML qualifies -- real SPA shells ship heavy inline JS
    # bundles (GitLab 433KB -> 38 words; the 25KB test shell -> 278 chars), while
    # small legitimate pages that merely carry a framework marker are compact
    # (adblock fixture: 269 raw -> 131 chars, 49% density) and must NOT escalate.
    return len(raw_html) >= 20000 and md_len < max(40, len(raw_html) * 0.02)


def html_to_clean_markdown(raw_html: str) -> str:
    """Ana içeriği (trafilatura) Markdown olarak çıkarır; kısa/boş sonuçta regex yedeğine düşer.
    Kalite kapısı: trafilatura regex'ten %50'den az kelime dönerse regex kullan (trafilatura aşırı filtrelemiş)."""
    if not raw_html or not raw_html.strip():
        return ""
    if trafilatura is not None:
        extracted = trafilatura.extract(
            raw_html,
            output_format="markdown",
            include_links=True,
            include_tables=True,
            include_formatting=True,
            favor_recall=True,
        )
        if extracted and len(extracted.strip()) >= _MIN_EXTRACTED_CHARS:
            regex_md = _regex_markdown(raw_html)
            # quality gate: if trafilatura kept < 50% of regex word count,
            # it dropped too much (sidebar, index pages, reference docs)
            if regex_md and len(extracted.split()) < len(regex_md.split()) * 0.5:
                return regex_md.strip()
            return extracted.strip()
    return _regex_markdown(raw_html)


def _regex_markdown(raw_html: str) -> str:
    """Ham HTML'den script/style gürültüsünü temizler, başlık ve linkleri koruyarak Markdown üretir."""

    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", raw_html, flags=re.S | re.I)
    text = re.sub(r"<(nav|header|footer|aside)\b[^>]*>.*?</\1>", "", text, flags=re.S | re.I)
    text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n# \1\n", text, flags=re.S | re.I)
    text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", text, flags=re.S | re.I)
    text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", text, flags=re.S | re.I)
    text = re.sub(
        r"""<a\s+[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""",
        r"[\2](\1)",
        text,
        flags=re.S | re.I,
    )
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", text, flags=re.S | re.I)
    text = re.sub(r"</p>|</div>|<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n\n".join(lines)


MAX_BODY_BYTES = 2 * 1024 * 1024
ROBOTS_TTL_S = 3600
_ROBOTS_CACHE: Dict[str, Any] = {}  # origin -> (parser, fetched_at)

# User-directed policy (2026-10-26): an explicit single-URL request is made by a
# human via a logged-in browser session, so robots.txt is reported as a note and
# the fetch proceeds. Automated crawling (browse jobs without user_directed) still
# honors robots. Site-level refusals (403/429/captcha/paywall) are NEVER bypassed.
_USER_DIRECTED: ContextVar[bool] = ContextVar("user_directed", default=False)


def is_user_directed() -> bool:
    return _USER_DIRECTED.get()


# Plain-HTTP egress policy for this request context. Default (False): reject
# private/loopback/link-local targets at every hop. A user-directed request may
# set allow_private_targets=True (the user's own logged-in session may
# legitimately reach an intranet target) — private targets are then permitted in
# THIS context only. The plain-HTTP fallback reads it via _egress_policy(); the
# API layer flips it per request with private_targets_allowed().
_ALLOW_PRIVATE: ContextVar[bool] = ContextVar("allow_private_targets", default=False)


@contextmanager
def private_targets_allowed(allowed: bool = True):
    """Permit (or deny) private fetch targets in this request context."""
    token = _ALLOW_PRIVATE.set(allowed)
    try:
        yield
    finally:
        _ALLOW_PRIVATE.reset(token)


def _egress_policy() -> EgressPolicy:
    return EgressPolicy(allow_literal=_ALLOW_PRIVATE.get())


class FetchBlocked(Exception):
    """Policy block (robots.txt / non-HTML / site refusal). Escalating to a heavier
    engine must NOT bypass it. Carries a stable machine-readable code so the API
    can surface *why* the fetch was refused instead of a vague failure."""

    def __init__(self, message: str, code: str = "blocked_by_site") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_MAX_HOPS = 10  # urllib's default redirect budget


def _check_hop(url: str, policy, egress=None):
    """Validate one fetch hop and return its Egress. Reuse `egress` when the
    caller already resolved this hop (the same host must never be resolved
    twice within one fetch)."""
    if egress is not None:
        return egress
    try:
        return policy.check_url(url)
    except EgressAddressError as exc:
        raise urllib.error.URLError(str(exc)) from exc
    except EgressDenied as exc:
        raise FetchBlocked(f"ssrf guard: {exc}", code="target_private_address") from exc


def _pinned_fetch(url, policy, timeout=15, headers=None, egress=None, max_hops=_MAX_HOPS):
    """Egress-checked fetch with DNS pinning: resolve ONCE per hop and CONNECT
    to that exact validated IP (closes the DNS-rebinding TOCTOU window of
    urlopen, which re-resolves at connect time). Every redirect hop is
    re-validated before it is followed. Returns an open response; caller closes.
    """
    current = url
    for _ in range(max_hops + 1):
        egress = _check_hop(current, policy, egress)
        req = urllib.request.Request(current, headers=headers or {})
        try:
            return pinned_opener(egress.ip).open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                raise
            location = exc.headers.get("Location") if exc.headers else None
            exc.close()
            if not location:
                raise FetchBlocked(f"redirect without location (HTTP {exc.code})",
                                   code="blocked_by_site") from exc
            current = urllib.parse.urljoin(current, location)
            egress = None  # the next hop re-resolves and re-validates
    raise FetchBlocked(f"too many redirects: {url}", code="blocked_by_site")


def _allowed_by_robots(url: str, user_agent: str, egress=None, policy=None) -> bool:
    """robots.txt check (512KB cap, cached in-memory 1h). Unreachable or
    missing robots.txt = allow all. The robots fetch itself rides the same
    pinned-IP egress path as the page fetch; `egress` reuses the caller's
    validated pin (same origin = one resolution)."""
    parts = urllib.parse.urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    cached = _ROBOTS_CACHE.get(origin)
    rp = cached[0] if cached and time.time() - cached[1] < ROBOTS_TTL_S else None
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = _pinned_fetch(origin + "/robots.txt", policy or _egress_policy(),
                                 timeout=10, headers={"User-Agent": user_agent}, egress=egress)
            with resp:
                rp.parse(resp.read(512 * 1024).decode("utf-8", errors="replace").splitlines())
        except Exception:  # shortcut: unreachable/missing robots.txt = allow all (cached ROBOTS_TTL_S), fail closed on 5xx if abuse appears
            rp.parse([])
        _ROBOTS_CACHE[origin] = (rp, time.time())
    return rp.can_fetch(user_agent, url)


def _default_url_raw(engine: str, url: str, session_name: str,
                     user_directed: Optional[bool] = None,
                     policy: Optional[EgressPolicy] = None) -> str:
    """Raw HTML fetch (plain HTTP). Honors robots.txt for automated crawl.

    ``user_directed=True`` marks an explicit single-URL request from the user
    (their own logged-in session): robots.txt is then skipped and reported as a
    note instead of a block. Site-level refusals (403/429/captcha/paywall) are
    still surfaced — only the robots policy bends for an explicit user request.

    Egress: the target is validated and PINNED (resolved once; the connect
    dials that exact IP) and every redirect hop is re-validated — a DNS answer
    that flips after validation can no longer reach a private address. Private
    targets are rejected unless the request context opted in via
    private_targets_allowed() (user's own logged-in session only).
    """
    if user_directed is None:
        user_directed = is_user_directed()
    policy = policy or _egress_policy()
    egress = _check_hop(url, policy)  # validate + pin BEFORE any request
    ua = f"HermesBrowserFarm/1.0 ({engine}; {session_name})"
    if not user_directed and not _allowed_by_robots(url, "HermesBrowserFarm", egress=egress, policy=policy):
        raise FetchBlocked(f"robots.txt disallows {url}", code="robots_disallowed")
    req_headers = {"User-Agent": ua, "Accept": "text/html,*/*;q=0.5"}
    try:
        resp = _pinned_fetch(url, policy, timeout=15, headers=req_headers, egress=egress)
    except urllib.error.HTTPError as exc:
        code, message = _classify_refusal(exc.code, exc.headers.get("Retry-After"), "")
        raise FetchBlocked(message or f"HTTP {exc.code}", code=code or "blocked_by_site")
    ctype = ""
    with resp:
        ctype = resp.headers.get("Content-Type", "")
        body = resp.read(MAX_BODY_BYTES)
    if "html" not in ctype.lower() and "xml" not in ctype.lower():
        raise FetchBlocked(f"non-HTML content type: {ctype}", code="non_html_content")
    text = body.decode("utf-8", errors="replace")
    code, message = _classify_refusal(200, None, text)
    if code:
        raise FetchBlocked(message, code=code)
    return text


def _default_url_driver(engine: str, url: str, session_name: str,
                        user_directed: Optional[bool] = None,
                        policy: Optional[EgressPolicy] = None) -> str:
    """Plain-HTTP fetch fallback (camofox tier and engines without binaries).
    Honors robots.txt unless user_directed (explicit single-URL request).
    Returns raw HTML — callers use html_to_clean_markdown() for agent output."""
    return _default_url_raw(engine, url, session_name, user_directed=user_directed, policy=policy)


def _classify_refusal(status: int, retry_after, text: str):
    """Map an HTTP status / page body to a stable access-block code.

    Returns (code, message); code is "" when the response is not a refusal.
    Marker-based detection is deliberately narrow (captcha / paywall) — we
    surface the refusal, we never attempt to bypass it.
    """
    if status == 403:
        return "blocked_by_site", "the target site refused this request (HTTP 403)"
    if status == 429:
        return "rate_limited_by_site", f"the target site rate-limited this request (HTTP 429, retry_after={retry_after})"
    if status in (401, 402):
        return "paywall_or_login_required", f"the target requires login or payment (HTTP {status})"
    body = (text or "").lower()
    # Only a real challenge WIDGET counts: an element/script that loads the
    # provider, not a mention of the word in prose or code comments.
    captcha_widgets = (
        'class="g-recaptcha"', "class='g-recaptcha'",
        'class="h-captcha"', "class='h-captcha'",
        "cf-challenge", "challenges.cloudflare.com/turnstile",
        "www.google.com/recaptcha/api.js", "js.hcaptcha.com/1/api.js",
    )
    if any(w in body for w in captcha_widgets):
        return "captcha_required", "the page requires a CAPTCHA challenge"
    # Paywall only when a blocking overlay/wall is present, not the phrase alone.
    paywall_walls = (
        'class="paywall"', "class='paywall'", "id=\"paywall\"",
        "paywall-overlay", "subscription-wall", "login-wall",
    )
    if any(w in body for w in paywall_walls):
        return "paywall_or_login_required", "the page requires login or subscription to read"
    return "", ""


def _adapter_result_to_task_result(job_id: str, res: AdapterResult, attempts: List[str]) -> Dict[str, Any]:
    """Translate an AdapterResult into the task-result dict shape."""
    return {
        "job_id": job_id,
        "session_name": "platform-adapter",
        "final_engine": f"platform-adapter:{res.adapter}",
        "attempted_engines": attempts,
        "oracle_passed": True,
        "adapter": res.adapter,
        "adapter_metadata": res.metadata,
        "markdown": res.markdown,
        "discovered_apis": [],
    }


class BrowserWorker:
    """Lightpanda -> Chromium Browser-Use -> Camofox kademeli yükseltme ve Self-Evolving Oracle işçisi."""

    ENGINE_LADDER = ["lightpanda", "chromium-browser-use", "camofox"]

    def __init__(
        self,
        driver_fn: Optional[Callable[[str, str, str], str]] = None,
        orchestrator: Optional[BrowserFarmOrchestrator] = None,
        adapter_registry: Optional[AdapterRegistry] = None,
    ) -> None:
        self.driver_fn = driver_fn or _default_url_driver
        self.orchestrator = orchestrator or BrowserFarmOrchestrator()
        self.adapter_registry = adapter_registry if adapter_registry is not None else default_registry()

    def execute_task(
        self,
        job_id: str,
        url: str,
        needs_vision: bool = False,
        js_complexity: str = "low",
        user_directed: bool = False,
    ) -> Dict[str, Any]:
        # user_directed: explicit single-URL request — robots.txt is skipped
        # (reported as a note) and site refusals are still surfaced. Propagated
        # via contextvar so any driver (adblock, CDP, plain-HTTP) picks it up
        # without changing the driver_fn contract. Scoped to THIS call: a leaked
        # user_directed=True would make later automated fetches skip robots too.
        token = _USER_DIRECTED.set(user_directed)
        try:
            return self._execute_task_impl(job_id, url, needs_vision, js_complexity, user_directed)
        finally:
            _USER_DIRECTED.reset(token)

    def _execute_task_impl(
        self,
        job_id: str,
        url: str,
        needs_vision: bool = False,
        js_complexity: str = "low",
        user_directed: bool = False,
    ) -> Dict[str, Any]:
        adapter_result = self.adapter_registry.run(url) if self.adapter_registry is not None else None
        if adapter_result is not None:
            return _adapter_result_to_task_result(job_id, adapter_result, [f"platform-adapter:{adapter_result.adapter}"])

        spec = self.orchestrator.build_session_task(
            job_id=job_id,
            url=url,
            needs_vision=needs_vision,
            js_complexity=js_complexity,
        )
        initial_engine = spec["engine"]
        start_idx = (
            self.ENGINE_LADDER.index(initial_engine)
            if initial_engine in self.ENGINE_LADDER
            else 0
        )
        engines_to_try = self.ENGINE_LADDER[start_idx:]

        attempts: List[str] = []
        for engine in engines_to_try:
            attempts.append(engine)
            try:
                raw_html = self.driver_fn(engine, url, spec["session_name"])
            except FetchBlocked as blocked:
                return {
                    "job_id": job_id,
                    "session_name": spec["session_name"],
                    "final_engine": engine,
                    "attempted_engines": attempts,
                    "oracle_passed": False,
                    "blocked": True,
                    "blocked_code": blocked.code,
                    "blocked_message": str(blocked),
                    "markdown": "",
                    "discovered_apis": [],
                }
            except Exception:
                raw_html = ""

            md = html_to_clean_markdown(raw_html)
            discovered_apis = discover_har_api_endpoints(raw_html, base_url=url)
            is_shell = looks_like_js_app_shell(raw_html, md)
            if len(md.strip()) >= MIN_ACCEPT_CHARS and not is_shell:
                self.orchestrator.record_domain_escalation(
                    url=url,
                    attempted_engines=attempts,
                    final_engine=engine,
                    discovered_apis=discovered_apis,
                )
                return {
                    "job_id": job_id,
                    "session_name": spec["session_name"],
                    "final_engine": engine,
                    "attempted_engines": attempts,
                    "oracle_passed": True,
                    "markdown": md,
                    "discovered_apis": discovered_apis,
                }

        return {
            "job_id": job_id,
            "session_name": spec["session_name"],
            "final_engine": attempts[-1] if attempts else initial_engine,
            "attempted_engines": attempts,
            "oracle_passed": False,
            "markdown": "",
            "discovered_apis": [],
        }
