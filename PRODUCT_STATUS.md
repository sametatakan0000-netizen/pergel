# Product status — browser engine SaaS (verified slices only)

Run tests: `.venv/bin/python -m unittest discover -s tests -t .` (269 pass; tests are hermetic — `*.example.com` DNS is stubbed and no test touches the real network; system python skips the trafilatura + playwright tests).

## Verified real (2026-10-24, host)
- Search: SearXNG in Docker (`searxng`, 127.0.0.1:8888, `restart unless-stopped`, config `~/.local/share/searxng/settings.yml`). Fan-out returned 10 deduped cited sources for a TR/EN query.
- Fetch+extract: real fetch of lightpanda.io via the HTTP driver -> 6007 chars clean markdown; github.com page -> 15807 chars.
- Policy: robots.txt (cached, `ROBOTS_TTL_S=1h`), 2 MB cap, content-type guard, SSRF guard, policy blocks never escalate.
- Engines (2026-10-24): tier-1 `lightpanda` 1.1.0-nightly (`~/.local/bin/lightpanda`, `fetch --dump html`) + tier-2 Chromium (Playwright 1.64 headless shell 156) installed and verified against a local HTTP server. Wired via `src/browser_engine/engine_drivers.py` (`engine_driver`, server default since today); failure/empty output escalates the ladder, robots.txt checked before any engine runs. Tests: `tests/test_engine_drivers.py` (stub-binary unit + real-engine integration).
- HAR/XHR discovery false positives fixed: `<link>/<meta>` manifests stripped, trailing escape residue (`\n`… and `\\`) removed from candidates.

## Not real yet
- tier-3 `camofox` deliberately deferred (stealth, legal/ToS opt-in) -> falls back to plain-HTTP driver.
- Chromium pool (2026-10-24): persistent headless browser owned by a single worker thread, fresh page per fetch, dead-engine auto-relaunch (`engine_drivers.py`). lightpanda stays per-fetch subprocess (CLI model).
- SaaS auth: `/v1/jobs/*` requires `Authorization: Bearer $BROWSE_API_KEY` when the env var is set (constant-time compare). Router paths (`/v1/chat/completions`, `/v1/router/*`, `/v1/models`) intentionally stay open for Hermes.
- Rate limiting (2026-10-24): per-client token bucket on `/v1/jobs/*` + `/v1/search/fanout` (`ORACLE_JOBS_RPM`, default 60, 0=off; 429 with Retry-After). Router paths unthrottled.
- Fan-out decomposition: lexical split on explicit conjunctions/punctuation only; no mid-phrase cuts. Semantic LLM split available and opt-in (`ORACLE_FANOUT_LLM=1`): one tiny call to the cheapest served priced model per fan-out (live-verified: 63+53 tokens ≈ $0.00001), used only when lexical yields a single long query; garbage/errors fall back to lexical; response carries `decomposition: llm|lexical`. Default OFF (no hidden model calls).
- MCP tool surface (2026-10-24): `src/mcp_server.py` (FastMCP, stdio) wraps the REST API: `browse_url`, `search_fanout`, `list_models`, `router_health`. Verified live: browse_url -> lightpanda markdown via the running router; search_fanout -> 5 live sources. Bearer key: `BROWSE_API_KEY` env wins, else `~/.config/oracle-router/browse_api.env`.
- Router spend is cache-aware (2026-10-24: `upstream_events.cached_tokens` + `cost_model.turn_cost_usd`; cached prompt tokens priced at `list_cost_cache_read`). `scripts/context_cost_guard.py` reports 24h spend-by-model + cache ratio + verdicts with zero model calls. `spent_today` is still an estimate against billed rates (Portal discount lives in `pricing.original`).

## Benchmark & REA track (target plan §3/§3b, 2026-10-25)
- Fidelity micro-suite (`src/bench/suites/fidelity.py`, no-LLM, 4 cases on the fixture server) — caught and fixed a real discovery-regex recall gap (segment-style `fetch('/api/product')` paths were invisible; `d69ae76`).
- `bench/reported.json` + loader in `report.py` (`6ba5d0d`): vendor/third-party figures live in their own "Reported by others — not reproduced here" section; entries without `source_url`/`retrieved` are rejected.
- `src/bench/suites/browserbench.py` (`0b427e4`): Speedometer 3.1 / JetStream 3.0 score parsers + `run_suite()`; automation hooks read from the suites' own sources (recorded in the module docstring); Lightpanda = `n/a (unsupported Web APIs)`, never 0. Live run = manual receipt.
- `docs/rea/README.md` (A5.1): REA rules, US/EU/TR legal basis, responsible-disclosure policy, per-vendor risk column (default `observe-only`; `dynamic-ok` needs a per-row user go).

## Adblock enforcement integration (target plan core, 2026-10-25)
The isolated rule layers are now one enforceable fetch path, not standalone modules:
- `src/browser_engine/adblock_session.py` — `AdblockBundle` + `compile_adblock` + `load_adblock_bundle` compose all four layers (network DNR, cosmetic CSS, scriptlets, procedural DOM) into one bundle; `build_injection` packages the 3 renderer layers as a single `document-start` JS. `load_adblock_bundle` compiles real EasyList + uAssets (~92k lines) into all layers in ~0.35s and blocks live ad endpoints (googlesyndication/doubleclick).
- `src/browser_engine/cdp_adblock_driver.py` — `AdblockBrowserSession` runs a real headless Chromium over CDP (WebSocket, `Fetch` interception + `Page.addScriptToEvaluateOnNewDocument`) and enforces all four layers on fetch+browse. `make_adblock_driver(bundle)` adapts it to the blocking `driver_fn(engine, url, session) -> raw_html` contract.
- Wired into the product: `BrowserWorker.html_to_clean_markdown` runs ad-free markdown through the adblock driver (proved end-to-end). **Default-on** (2026-10-25): `_resolve_driver` enforces whenever the durable filter lists (`~/.local/share/browser_farm/filterlists/*.txt`) exist. `ORACLE_ADBLOCK_LISTS` selects `os.pathsep`-joined custom paths or `off`; missing lists fall back to `engine_driver` so the product never breaks; `_with_fallback` fails open on availability (Chromium/CDP failure) while policy blocks still never escalate. Tests: `test_adblock_session`, `test_adblock_live`, `test_cdp_adblock_driver_live`, `test_worker_adblock_integration`, `test_adblock_real_lists`, `test_adblock_default_on` (412/412 pass).

## Platform adapters (structured-API-first fetch, 2026-10-26)
Before falling back to the engine ladder, `execute_task` now tries platform adapters that pull from official/structured APIs — cheaper, cleaner, and immune to bot-walls (`src/browser_engine/platform_adapters.py`, `a9bc973`):
- `AdapterRegistry` + `NpmAdapter`/`GithubAdapter`, each `can_handle(url)` + `fetch(url, get) -> AdapterResult|None`. `None` = fall through to the generic ladder.
- Injectable JSON getter (unit tests pass a fake); default `_http_get_json` is SSRF-safe: https-only, allow-listed API hosts (`registry.npmjs.org`, `api.github.com`), 10s timeout, 2MB cap. No credentials read/logged.
- Worker short-circuit: on adapter match the result carries `adapter`, `adapter_metadata`, `final_engine=platform-adapter:<name>` and the engine ladder never runs. Verified live: `npmjs.com/package/left-pad` -> 982 chars, `github.com/python/cpython` -> 8999 chars, `example.com` -> None (falls through).
- Tests: `test_platform_adapters.py` + `test_worker_platform_adapters.py` (15 tests). Full non-live suite: **493 passed** (verified run 2026-10-26).
- Next in this layer (not yet built): YouTube transcript adapter (youtube-transcript-api / yt-dlp), oEmbed for generic video/article pages, RSS/sitemap for news.

## Known flaky (pre-existing, 2026-10-26)
- `tests/test_cosmetic_timing.py::TestCosmeticDocumentStart::test_late_injection_is_observable` fails intermittently (~2/5 runs) in a visibility probe ("probe never saw the ad even with late injection"). **Pre-dates** the platform-adapter work (reproduced with worker changes stashed: 4/5 pass without, 3/5 with — same instability either way). Not caused by `a9bc973`. Needs a timing/latency fix in the cosmetic injection visibility check.

## Still pending / awaits user (blocked on HFY input)
1. `hermes login` to reconnect the Nous Portal connector (sticky fallback is covering meanwhile).
2. Three cross-vendor evaluations for that connector's review (0/3 done).
3. ~~A8 machine-access questions~~ — withdrawn (2026-10-25): REA scope is market-wide (all browsers + all OS/ISO images), run on our own machine under HFY's blanket approval; no external lab needed.

## Known side effects (2026-10-25)
- Post-restart spend is MiMo-cache-shaped ($0.18 / 102 turns): ~37% cached-context turns; per-turn cap effective (~$0.018 max).
- `spent_today` still runs at list rate in `spent_today_usd` (that's what brakes see); `guard` shows the cache-aware number for humans.
- Playwright hard requirement in 5 tests can fail under system python; venv run keeps 269/269.
