"""Kademeli Motor Yükseltmeli (Engine Cascading) Tarayıcı İşçisi ve HAR/XHR API Keşfedici."""
import html
import re
import urllib.parse
import urllib.robotparser
import urllib.request
from typing import Any, Callable, Dict, List, Optional
from src.browser_engine.browser_orchestrator import BrowserFarmOrchestrator


def _strip_non_script_tags(raw_html: str) -> str:
    """Drop <link>/<meta> tags (icons, manifests, canonical) that are not API calls."""
    return re.sub(r"<(?:link|meta)\b[^>]*>", "", raw_html, flags=re.IGNORECASE)


def discover_har_api_endpoints(raw_html: str, base_url: str = "") -> List[str]:
    """`har-derived-api-client` desenine uygun olarak sayfa kaynağındaki XHR/JSON API uçlarını keşfeder."""
    # shortcut: regex, not a DOM/JS parser; only quoted strings inside JS network calls
    # or script blocks count, so <link> icons/manifests are not reported as APIs.
    pattern = re.compile(
        r"""(?:fetch|axios\.(?:get|post)|XMLHttpRequest|["'])((?:https?://|/)[^"'\s)<>]+?(?:api|graphql|\.json)[^"'\s)<>]*)["']""",
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
except ImportError:  # shortcut: regex fallback is boilerplate-blind, require trafilatura in production deploys
    trafilatura = None

_MIN_EXTRACTED_CHARS = 80  # shorter results are usually fragments/SPA shells; regex path keeps them


def html_to_clean_markdown(raw_html: str) -> str:
    """Ana içeriği (trafilatura) Markdown olarak çıkarır; kısa/boş sonuçta regex yedeğine düşer."""
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
            return extracted.strip()
    return _regex_markdown(raw_html)


def _regex_markdown(raw_html: str) -> str:
    """Ham HTML'den script/style gürültüsünü temizler, başlık ve linkleri koruyarak Markdown üretir."""

    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", raw_html, flags=re.S | re.I)
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
_ROBOTS_CACHE: Dict[str, Any] = {}


class FetchBlocked(Exception):
    """Policy block (robots.txt / non-HTML). Escalating to a heavier engine must NOT bypass it."""


def _allowed_by_robots(url: str, user_agent: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    rp = _ROBOTS_CACHE.get(origin)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": user_agent})
            with urllib.request.urlopen(req, timeout=10) as resp:
                rp.parse(resp.read(512 * 1024).decode("utf-8", errors="replace").splitlines())
        except Exception:  # shortcut: unreachable/missing robots.txt = allow all, cache never expires; add TTL when long-running
            rp.parse([])
        _ROBOTS_CACHE[origin] = rp
    return rp.can_fetch(user_agent, url)


def _default_url_driver(engine: str, url: str, session_name: str) -> str:
    """Plain-HTTP fetch fallback (camofox tier and engines without binaries). Honors robots.txt."""
    ua = f"HermesBrowserFarm/1.0 ({engine}; {session_name})"
    if not _allowed_by_robots(url, "HermesBrowserFarm"):
        raise FetchBlocked(f"robots.txt disallows {url}")
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html,*/*;q=0.5"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # HTTPError (403/5xx) propagates -> worker escalates
        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype.lower() and "xml" not in ctype.lower():
            raise FetchBlocked(f"non-HTML content type: {ctype}")
        return resp.read(MAX_BODY_BYTES).decode("utf-8", errors="replace")


class BrowserWorker:
    """Lightpanda -> Chromium Browser-Use -> Camofox kademeli yükseltme ve Self-Evolving Oracle işçisi."""

    ENGINE_LADDER = ["lightpanda", "chromium-browser-use", "camofox"]

    def __init__(
        self,
        driver_fn: Optional[Callable[[str, str, str], str]] = None,
        orchestrator: Optional[BrowserFarmOrchestrator] = None,
    ) -> None:
        self.driver_fn = driver_fn or _default_url_driver
        self.orchestrator = orchestrator or BrowserFarmOrchestrator()

    def execute_task(
        self,
        job_id: str,
        url: str,
        needs_vision: bool = False,
        js_complexity: str = "low",
    ) -> Dict[str, Any]:
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
            except FetchBlocked:
                return {
                    "job_id": job_id,
                    "session_name": spec["session_name"],
                    "final_engine": engine,
                    "attempted_engines": attempts,
                    "oracle_passed": False,
                    "blocked": True,
                    "markdown": "",
                    "discovered_apis": [],
                }
            except Exception:
                raw_html = ""

            md = html_to_clean_markdown(raw_html)
            discovered_apis = discover_har_api_endpoints(raw_html, base_url=url)
            if len(md.strip()) >= 10:
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
