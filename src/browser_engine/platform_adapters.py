"""Platform adapters: structured/official sources tried before the browser ladder.

Each adapter claims URLs via can_handle(), fetches from an official JSON API
through an injected getter, and returns AdapterResult or None. None means
"fall through to the generic engine ladder". Only allow-listed API hosts are
ever requested (SSRF guard), and no credentials are read or logged here.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

ALLOWED_API_HOSTS = frozenset({
    "registry.npmjs.org",
    "api.github.com",
    "www.youtube.com",
    "vimeo.com",
    "graph.facebook.com",
})
_MAX_BYTES = 2 * 1024 * 1024


@dataclass
class AdapterResult:
    adapter: str
    url: str
    markdown: str
    metadata: Dict


def _safe_api_url(url: str) -> Optional[str]:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.hostname not in ALLOWED_API_HOSTS:
        return None
    return url


def _http_get_json(api_url: str):
    safe = _safe_api_url(api_url)
    if safe is None:
        return None
    req = urllib.request.Request(
        safe,
        headers={"Accept": "application/json", "User-Agent": "ai-browser-farm-adapter/1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read(_MAX_BYTES + 1)[:_MAX_BYTES]
        return json.loads(body.decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def _safe_target_url(url: str) -> Optional[str]:
    """SSRF guard for target-site fetches (RSS/sitemap): HTTPS only, and never a
    private/loopback/link-local host. Unlike the API allow-list, the host here is
    the target site itself (its own feed endpoints), so we block internal ranges
    instead of restricting to a fixed list."""
    import ipaddress
    import socket

    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname:
        return None
    try:
        infos = socket.getaddrinfo(parts.hostname, None)
    except (socket.gaierror, OSError, ValueError):
        return None
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            return None
    return url


def _http_get_text(url: str) -> Optional[str]:
    safe = _safe_target_url(url)
    if safe is None:
        return None
    req = urllib.request.Request(
        safe,
        headers={"Accept": "application/xml, text/xml, */*", "User-Agent": "ai-browser-farm-adapter/1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read(_MAX_BYTES + 1)[:_MAX_BYTES]
        return body.decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


class NpmAdapter:
    name = "npm"
    _PKG = re.compile(r"^https://www\.npmjs\.com/package/((?:@[^/]+/)?[^/?#]+)/?$")

    def can_handle(self, url: str) -> bool:
        return bool(self._PKG.match(url))

    def fetch(self, url: str, get: Callable[[str], object]) -> Optional[AdapterResult]:
        m = self._PKG.match(url)
        if not m:
            return None
        name = m.group(1)
        data = get(f"https://registry.npmjs.org/{name.replace('/', '%2F')}")
        if not isinstance(data, dict) or not data.get("name"):
            return None
        latest = (data.get("dist-tags") or {}).get("latest", "")
        lines = [f"# {data.get('name')}"]
        if latest:
            lines.append(f"Latest: {latest}")
        if data.get("description"):
            lines.append(str(data["description"]))
        if data.get("license"):
            lines.append(f"License: {data['license']}")
        if data.get("homepage"):
            lines.append(f"Homepage: {data['homepage']}")
        readme = data.get("readme") or ""
        if readme and readme.strip() and readme.strip() != "ERROR: No README data found!":
            lines.append("")
            lines.append(readme.strip())
        return AdapterResult(
            adapter=self.name,
            url=url,
            markdown="\n".join(lines).strip() + "\n",
            metadata={"package": data.get("name"), "latest": latest},
        )


class GithubAdapter:
    name = "github"
    _REPO = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)/?$")
    _RESERVED = frozenset({"settings", "orgs", "login", "marketplace", "topics",
                           "explore", "features", "sponsors", "notifications"})

    def can_handle(self, url: str) -> bool:
        m = self._REPO.match(url)
        return bool(m) and m.group(1).lower() not in self._RESERVED

    def fetch(self, url: str, get: Callable[[str], object]) -> Optional[AdapterResult]:
        m = self._REPO.match(url)
        if not m or m.group(1).lower() in self._RESERVED:
            return None
        owner, repo = m.group(1), m.group(2)
        meta = get(f"https://api.github.com/repos/{owner}/{repo}")
        if not isinstance(meta, dict) or not meta.get("full_name"):
            return None
        lines = [f"# {meta['full_name']}"]
        if meta.get("description"):
            lines.append(str(meta["description"]))
        if "stargazers_count" in meta:
            lines.append(f"Stars: {meta['stargazers_count']}")
        lic = (meta.get("license") or {}).get("spdx_id")
        if lic:
            lines.append(f"License: {lic}")
        readme_obj = get(f"https://api.github.com/repos/{owner}/{repo}/readme")
        if isinstance(readme_obj, dict) and readme_obj.get("encoding") == "base64":
            try:
                text = base64.b64decode(readme_obj.get("content", "")).decode("utf-8", "replace")
                if text.strip():
                    lines.append("")
                    lines.append(text.strip())
            except (ValueError, TypeError):
                pass
        return AdapterResult(
            adapter=self.name,
            url=url,
            markdown="\n".join(lines).strip() + "\n",
            metadata={"full_name": meta["full_name"]},
        )


class YoutubeTranscriptAdapter:
    """Fetch a video's official transcript (captions) before any rendering.

    Uses youtube-transcript-api when available (dependency-injected fetcher in
    tests). Returns None when no transcript exists so the engine ladder or the
    oEmbed adapter can take over.
    """

    name = "youtube-transcript"
    _YT = re.compile(
        r"^https://(?:www\.|m\.)?youtube\.com/(?:watch\?(?:[^#]*&)?v=|shorts/|embed/)"
        r"([\w-]{6,})"
        r"|^https://youtu\.be/([\w-]{6,})"
    )

    def __init__(self, fetcher: Optional[Callable] = None) -> None:
        self._fetcher = fetcher

    def extract_video_id(self, url: str) -> Optional[str]:
        m = self._YT.match(url)
        if not m:
            return None
        return m.group(1) or m.group(2)

    def can_handle(self, url: str) -> bool:
        return self.extract_video_id(url) is not None

    def _default_fetch(self, video_id: str, languages=("en",)):
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError:
            return None
        try:
            fetched = YouTubeTranscriptApi().fetch(video_id, languages=languages)
            return [s.text for s in fetched]
        except Exception:
            return None

    def fetch(self, url: str, get: Callable[[str], object]) -> Optional[AdapterResult]:
        video_id = self.extract_video_id(url)
        if video_id is None:
            return None
        fetcher = self._fetcher or self._default_fetch
        segments = fetcher(video_id)
        if not segments:
            return None
        text = "\n".join(s.strip() for s in segments if s and s.strip())
        if not text:
            return None
        return AdapterResult(
            adapter=self.name,
            url=url,
            markdown=text + "\n",
            metadata={"video_id": video_id, "segments": len(segments)},
        )


class OEmbedAdapter:
    """Known-provider oEmbed endpoints only (no arbitrary-site discovery).

    Arbitrary hosts are never requested: the target page itself is not fetched,
    only the provider's official oEmbed JSON endpoint on an allow-listed host.
    """

    name = "oembed"
    _YT = re.compile(r"^https://(?:www\.|m\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]{6,}")
    _VIMEO = re.compile(r"^https://vimeo\.com/\d+/?$")
    _IG = re.compile(r"^https://(?:www\.)?instagram\.com/(?:p|reel|tv)/[\w-]+/?")

    def _endpoint(self, url: str) -> Optional[str]:
        q = urllib.parse.quote(url, safe="")
        if self._YT.match(url):
            return f"https://www.youtube.com/oembed?url={q}&format=json"
        if self._VIMEO.match(url):
            return f"https://vimeo.com/api/oembed.json?url={q}"
        if self._IG.match(url):
            return f"https://graph.facebook.com/v26.0/instagram_oembed?url={q}"
        return None

    def can_handle(self, url: str) -> bool:
        return self._endpoint(url) is not None

    def fetch(self, url: str, get: Callable[[str], object]) -> Optional[AdapterResult]:
        endpoint = self._endpoint(url)
        if endpoint is None:
            return None
        data = get(endpoint)
        if not isinstance(data, dict):
            return None
        if not (data.get("title") or data.get("author_name")
                or data.get("provider_name") or data.get("html")):
            return None
        lines = []
        if data.get("title"):
            lines.append(f"# {data['title']}")
        if data.get("author_name"):
            lines.append(f"Author: {data['author_name']}")
        if data.get("provider_name"):
            lines.append(f"Provider: {data['provider_name']}")
        if data.get("type"):
            lines.append(f"Type: {data['type']}")
        return AdapterResult(
            adapter=self.name,
            url=url,
            markdown="\n".join(lines).strip() + "\n",
            metadata={"oembed_url": endpoint, "type": data.get("type")},
        )


class RssSitemapAdapter:
    """Last-resort structured fetch: a site's own RSS/Atom feed or sitemap.

    Unlike API adapters, the host here is the target site itself, so SSRF is
    enforced by _safe_target_url (HTTPS + no private/reserved IPs) rather than a
    fixed allow-list. Feed endpoints are probed in order; sitemap is fallback.
    """

    name = "rss"
    default_getter = staticmethod(lambda url: _http_get_text(url))
    _SITE = re.compile(r"^https?://[^/]+/?$")
    _FEED_PATHS = ("feed", "rss", "rss.xml", "atom.xml", "feed.xml", "index.xml")
    _SITEMAP_PATHS = ("sitemap.xml",)

    def can_handle(self, url: str) -> bool:
        return bool(self._SITE.match(url))

    def _probe(self, base: str, paths, get: Callable[[str], object], tag: str):
        for path in paths:
            text = get(f"{base}{path}")
            if isinstance(text, str) and text.strip():
                return self._render(text, f"{base}{path}", tag)
        return None

    def _render(self, xml: str, source_url: str, tag: str) -> Optional[AdapterResult]:
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(xml.strip())
        except ET.ParseError:
            return None
        ns = {"atom": "http://www.w3.org/2005/Atom",
              "sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        items = root.findall(".//item") or root.findall("atom:entry", ns)
        if items:
            lines = [f"# Feed: {source_url}"]
            count = 0
            for it in items[:20]:
                title = (it.findtext("title") or it.findtext("atom:title", namespaces=ns) or "").strip()
                desc = (it.findtext("description") or it.findtext("atom:summary", namespaces=ns) or "").strip()
                if not title:
                    continue
                count += 1
                lines.append(f"- {title}")
                if desc:
                    lines.append(f"  {desc}")
            if count:
                return AdapterResult(adapter=tag, url=source_url,
                                     markdown="\n".join(lines) + "\n",
                                     metadata={"items": count, "source": source_url})
            return None
        urls = root.findall(".//sm:url/sm:loc", ns) or root.findall(".//url/loc")
        if urls:
            lines = [f"# Sitemap: {source_url}"]
            locs = [(u.text or "").strip() for u in urls[:50] if (u.text or "").strip()]
            if not locs:
                return None
            lines.extend(f"- {loc}" for loc in locs)
            return AdapterResult(adapter=tag, url=source_url,
                                 markdown="\n".join(lines) + "\n",
                                 metadata={"urls": len(locs), "source": source_url})
        return None

    def fetch(self, url: str, get: Callable[[str], object]) -> Optional[AdapterResult]:
        base = url if url.endswith("/") else url + "/"
        res = self._probe(base, self._FEED_PATHS, get, "rss")
        if res is not None:
            return res
        return self._probe(base, self._SITEMAP_PATHS, get, "sitemap")


class WaybackAdapter:
    """Archived fallback: Internet Archive Wayback Machine (official, free).

    Used for sites with no readable channel left (Reddit .json is 403 since
    May 2026, LinkedIn has no public read API) or pages that disappeared. The
    Availability API returns the closest snapshot; we fetch its raw replay body.
    Hosts are fixed and allow-listed — the target URL is only ever a query param.
    """

    name = "wayback"
    default_getter = staticmethod(_http_get_text)
    _WAYBACK_HOST = "archive.org"
    _WAYBACK_REPLAY = "web.archive.org"

    def can_handle(self, url: str) -> bool:
        low = url.lower()
        if "web.archive.org" in low:
            return True
        # Sites with no structured/readable channel -> archived path.
        return any(h in low for h in ("reddit.com/", "linkedin.com/posts/"))

    def _html_to_markdown(self, html: str) -> str:
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
        for tag in ("h1", "h2", "h3"):
            text = re.sub(rf"(?is)<{tag}[^>]*>(.*?)</{tag}>", r"\n## \1\n", text)
        text = re.sub(r"(?is)<p[^>]*>", "\n", text)
        text = re.sub(r"(?s)<[^>]+>", "", text)
        text = re.sub(r"[ \t]+", " ", text)
        return "\n".join(l.strip() for l in text.splitlines() if l.strip()) + "\n"

    def fetch(self, url: str, get: Callable[[str], object]) -> Optional[AdapterResult]:
        import urllib.parse

        # Resolve target: strip a leading web.archive.org/<ts>/<mode>/ wrapper.
        target = url
        m = re.match(r"^(?:https?://)?web\.archive\.org/(?:web/)?\d+\w*/(https?://.+)$", url)
        if m:
            target = m.group(1)

        api = "https://archive.org/wayback/available?url=" + urllib.parse.quote(target, safe="")
        data = get(api)
        if isinstance(data, (bytes, bytearray)):
            data = bytes(data).decode("utf-8", "replace")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                return None
        if not isinstance(data, dict):
            return None
        closest = (data.get("archived_snapshots") or {}).get("closest") or {}
        if not closest.get("available"):
            return None
        ts = closest.get("timestamp", "")
        if not ts:
            return None

        raw = f"https://web.archive.org/web/{ts}id_/{target}"
        body = get(raw)
        if isinstance(body, (bytes, bytearray)):
            body = bytes(body).decode("utf-8", "replace")
        if not isinstance(body, str) or not body.strip():
            return None

        markdown = self._html_to_markdown(body)
        return AdapterResult(
            adapter=self.name, url=target, markdown=markdown,
            metadata={"timestamp": ts, "snapshot": closest.get("url"), "source": raw},
        )


class AdapterRegistry:
    def __init__(self, adapters: List) -> None:
        self.adapters = list(adapters)

    def match(self, url: str):
        for a in self.adapters:
            if a.can_handle(url):
                return a
        return None

    def run(self, url: str, get: Optional[Callable[[str], object]] = None) -> Optional[AdapterResult]:
        adapter = self.match(url)
        if adapter is None:
            return None
        return adapter.fetch(url, get or getattr(adapter, "default_getter", _http_get_json))


def default_registry() -> AdapterRegistry:
    return AdapterRegistry([NpmAdapter(), GithubAdapter(), YoutubeTranscriptAdapter(),
                            OEmbedAdapter(), RssSitemapAdapter(), WaybackAdapter()])
