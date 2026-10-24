# Product status — browser engine SaaS (verified slices only)

Run tests: `.venv/bin/python -m unittest discover -s tests -t .` (170 pass; system python skips the trafilatura + playwright tests).

## Verified real (2026-10-24, host)
- Search: SearXNG in Docker (`searxng`, 127.0.0.1:8888, `restart unless-stopped`, config `~/.local/share/searxng/settings.yml`). Fan-out returned 10 deduped cited sources for a TR/EN query.
- Fetch+extract: real fetch of lightpanda.io via the HTTP driver -> 6007 chars clean markdown; github.com page -> 15807 chars.
- Policy: robots.txt, 2 MB cap, content-type guard, SSRF guard, policy blocks never escalate.
- Engines (2026-10-24): tier-1 `lightpanda` 1.1.0-nightly (`~/.local/bin/lightpanda`, `fetch --dump html`) + tier-2 Chromium (Playwright 1.64 headless shell 156) installed and verified against a local HTTP server. Wired via `src/browser_engine/engine_drivers.py` (`engine_driver`, server default since today); failure/empty output escalates the ladder, robots.txt checked before any engine runs. Tests: `tests/test_engine_drivers.py` (stub-binary unit + real-engine integration).
- HAR/XHR discovery false positives fixed: `<link>/<meta>` manifests stripped, trailing escape residue (`\n`… and `\\`) removed from candidates.

## Not real yet
- tier-3 `camofox` deliberately deferred (stealth, legal/ToS opt-in) -> falls back to plain-HTTP driver.
- Chromium pool (2026-10-24): persistent headless browser owned by a single worker thread, fresh page per fetch, dead-engine auto-relaunch (`engine_drivers.py`). lightpanda stays per-fetch subprocess (CLI model).
- SaaS auth: `/v1/jobs/*` requires `Authorization: Bearer $BROWSE_API_KEY` when the env var is set (constant-time compare). Router paths (`/v1/chat/completions`, `/v1/router/*`, `/v1/models`) intentionally stay open for Hermes.
- Rate limiting (2026-10-24): per-client token bucket on `/v1/jobs/*` + `/v1/search/fanout` (`ORACLE_JOBS_RPM`, default 60, 0=off; 429 with Retry-After). Router paths unthrottled.
- Fan-out decomposition: lexical split on explicit conjunctions/punctuation only; no mid-phrase cuts. Semantic LLM split available and opt-in (`ORACLE_FANOUT_LLM=1`): one tiny call to the cheapest served priced model per fan-out (live-verified: 63+53 tokens ≈ $0.00001), used only when lexical yields a single long query; garbage/errors fall back to lexical; response carries `decomposition: llm|lexical`. Default OFF (no hidden model calls).
- MCP tool surface (2026-10-24): `src/mcp_server.py` (FastMCP, stdio) wraps the REST API: `browse_url`, `search_fanout`, `list_models`, `router_health`. Verified live: browse_url -> lightpanda markdown via the running router; search_fanout -> 5 live sources. Bearer key: `BROWSE_API_KEY` env wins, else `~/.config/oracle-router/browse_api.env`.
- Router `spent_today` prices every prompt token at the plain input rate: cache-read/write split not recorded (`prompt_tokens_details` dropped at `record_upstream`) — spend figure is an upper-mid estimate.
