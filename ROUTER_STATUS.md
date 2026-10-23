# Router status — prototype, verified slices only

This repository does **not** modify the running Hermes gateway or its default model.

## What is real now

- **Model registry (`src/router/model_registry.py`)** — built from public, key-less data; no model is ever called to profile it.
  - Membership, capabilities and **Portal billed prices**: `https://inference-api.nousresearch.com/v1/models` (425 models; `pricing` = billed, `pricing.original` = list → discount).
  - Benchmarks: OpenRouter `/api/v1/models` → Artificial Analysis intelligence/coding/agentic indices (matched by ID, `:free` falls back to base ID).
  - Curation: Hermes `model-catalog.json` (56/57 curated IDs present on Nous).
  - Auto-pool = curated IDs + their `:free` variants. `:batch` (half price, interactive behaviour unverified) and region-pinned `:US` variants are explicit-only.
  - Fallbacks: catalog × OpenRouter, then catalog × models.dev. Snapshot written atomically; `serve` refreshes every 20 min and keeps the last snapshot on failure.
- **LiveRouter (`src/router/live_router.py`)** — deterministic, documented policy:
  - price tier from **billed** input price (≤0.3 / ≤1 / ≤3 / >3 USD per 1M); within a tier: published AA index × learned reliability, then price;
  - context-fit: conservative token estimate (images counted as 1.5K, not base64 bytes); models a request outgrows are skipped, so virtual profiles advertise their **largest** window (1.05M) to Hermes;
  - session affinity persisted (escalate-only); cleared on regenerate; 429/5xx → 5 min cooldown, 404 → 1 h; effort clamped to supported levels.
- **Self-evolution (`src/router/outcome_learning.py`)** — learns from real traffic, zero extra inference:
  - structural checks: malformed tool-call JSON, unknown tool names, empty answers (stream and non-stream);
  - implicit feedback on the next user turn: regenerate −1, correction phrasing −0.5, continuing after a final answer +0.5; tool-loop turns neutral; aux calls (explicit models sharing the session id) ignored;
  - decayed (14-day half-life) Beta reliability per model × bucket (`t{keyword tier}:{txt|img}:{s|m|l}`);
  - learned start-tier floors per bucket (raise when reliability < 0.4 over ≥5 observations; decay + 5% one-tier-lower exploration let floors come back down); every change logged in `evolution_events`;
  - non-stream self-healing: a structurally broken answer is retried on the next candidate before the client sees it;
  - inspect: `GET /v1/router/learning`.
- **Proxy (`src/api/server.py`)** — loopback only; forwards to `hermes proxy` (any bearer, proxy attaches the Portal credential); SSE line-by-line; dead proxy → 502/504 without model penalty; no registry → 422.
- **Host deployment (`scripts/host/`)** — `install_user_services.sh` (dry-run default; `--apply` copies `src/` at a pinned commit to `~/.local/share/oracle-router/app`, installs hardened systemd *user* units for `hermes proxy` and the router); `verify_live.sh` (free checks; `--spend-tokens` sends two tiny real requests and checks SSE tool calls).
- Legacy hand-written inventory (`oracle_router.py`, guessed profiles) has been removed.

Dry run with the real registry and an echo upstream: `python3 scripts/routing_dry_run.py` (no inference).

## Not verified yet

- **No real Nous inference through the router.** The agent's Docker sandbox cannot reach the host loopback (`127.0.0.1:8645`); this is expected — the router belongs on the host. Run the host steps below.
- Learning starts empty: quality ordering is benchmark-driven until real traffic accumulates evidence. The keyword tier guess is crude by design; floors correct it per bucket over time.
- Correction detection is a regex (TR/EN) — a weak signal by design (−0.5).

## Remote one-shot (from a remote-desktop session on the host)

```bash
bash ~/.hermes/sandboxes/docker/default/home/ai_browser_farm/scripts/host/remote_quickstart.sh
```
Installs + verifies (2 tiny real requests) + registers the provider; writes `host_quickstart.log`
into the repo so the sandboxed agent can read the result without copy/paste.

## Host steps (Ubuntu host, not the agent sandbox)

```bash
cd ~/.hermes/sandboxes/docker/default/home/ai_browser_farm
bash scripts/host/install_user_services.sh            # review
bash scripts/host/install_user_services.sh --apply    # install + start
bash scripts/host/verify_live.sh                      # free checks
bash scripts/host/verify_live.sh --spend-tokens       # 2 tiny real requests (< $0.0001)
ORACLE_ROUTER_APPLY=1 bash scripts/hermes_full_optimize_commands.sh   # register provider only
```

Then in a **new** Hermes session: `/model custom:oracle-router:oracle/auto`. The main model default is untouched until you choose `--global`.

Tests: `python3 -m unittest discover -s tests -t .` · Status: `python3 -m src.cli doctor` → `PROTOTYPE`.
