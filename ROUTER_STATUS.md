# Router status — prototype, verified slices only

This repository does **not** modify the running Hermes gateway or its default model.

## What is real now

- **Model registry (`src/router/model_registry.py`)** — membership from the official Hermes Nous catalog (57 IDs); capabilities from the public, key-less OpenRouter `/api/v1/models` endpoint (models.dev fallback). Per model: tool calling, image input, supported/default reasoning efforts, effective context (min of advertised and top-provider limit), list prices, Artificial Analysis intelligence/coding/agentic indices. **No model is called to build profiles.** 52/57 routable; 5 IDs without public metadata are `catalog_only` and never auto-selected. Snapshot written atomically to `model_registry.json`; `serve` refreshes every 20 min and keeps the last snapshot on failure.
- **LiveRouter (`src/router/live_router.py`)** — deterministic policy, documented in the module docstring:
  - price tier from list input price (≤0.3 / ≤1 / ≤3 / >3 USD per 1M) — a cost band, not a quality claim;
  - within a tier, higher published AA intelligence index first, then lower price;
  - `oracle/auto` classifies only the latest user message (Hermes sends tool schemas every turn, so tools are not a difficulty signal); images anywhere in history require image-capable models;
  - session affinity persisted in SQLite; sessions escalate but never downgrade (prompt-cache continuity);
  - 429/5xx → 5 min cooldown, 404 → 1 h; up to 3 candidates tried before any byte is streamed;
  - `reasoning_effort` clamped to the chosen model's supported levels (e.g. `medium` → `high` on GLM), dropped when unsupported.
- **Proxy (`src/api/server.py`)** — loopback only. Forwards to `hermes proxy` (`127.0.0.1:8645/v1`; docs: "use any bearer token, the proxy attaches your real credential"). Streams SSE line-by-line, records status/latency/token usage. Dead proxy → 502 (timeout → 504) with no model penalty. No registry → virtual profiles return 422 instead of guessing. Only `oracle/*` requests set session affinity: Hermes sends the same session id on auxiliary calls (titles, compression), which must not hijack the conversation model.
- `session_affinity_header: x-hermes-session-id` is a documented Hermes provider option; Hermes only sends it when configured.

Dry run on real registry with an echo upstream: `python3 scripts/routing_dry_run.py` (no inference, no cost).

## Not verified / known limits

- **No real Nous inference has gone through this router.** The Docker sandbox cannot reach the host's `:8645`; all forwarding tests use local HTTP fixtures.
- Prices are OpenRouter list prices; Portal promo/free pricing is not reflected (hence `oracle/free` → 422 today).
- Quality ranking uses published third-party benchmarks; there is no per-task outcome learning from real answers yet. Keyword tier classification is crude.
- Virtual profile `context_length` reported to Hermes is the smallest routable window (currently 200K) — safe, but compresses earlier than needed for large-context models.
- Legacy `DynamicOracleRouter` (hand-written guessed inventory) still exists for older tests/modules; it is **not** used by the proxy path.
- Other SaaS demo endpoints (browse/search/watchdog) remain simplified.

## Safe verification on the Hermes host

1. `hermes proxy start` (loopback), then `curl -f http://127.0.0.1:8645/v1/models`.
2. `python3 -m src.cli serve --db-dir <persistent dir>`; `curl -f http://127.0.0.1:8090/v1/health` → `status: ok`, `routable > 0`.
3. One cheap non-sensitive request through `/v1/chat/completions` with explicit model, then `oracle/auto`; check `X-Oracle-Selected-Model`, `usage`, and Portal billing. Test streaming + tool calls.
4. Then review `scripts/hermes_full_optimize_commands.sh` (dry-run by default; `ORACLE_ROUTER_APPLY=1` registers the provider only). Do not change `model.default` until steps 1–3 pass. Test via `/model` in a new session.

Tests: `python3 -m unittest discover -s tests -t .` · Status: `python3 -m src.cli doctor` → `PROTOTYPE`.
