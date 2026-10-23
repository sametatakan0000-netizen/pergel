# Router status — prototype, verified slices only

This repository does **not** modify the running Hermes gateway or its default model.

## What is real now

- **Model registry (`src/router/model_registry.py`)** — built from public, key-less data; no model is ever called to profile it.
  - Membership, capabilities and **Portal billed prices**: `https://inference-api.nousresearch.com/v1/models` (425 models; `pricing` = billed, `pricing.original` = list → discount).
  - Benchmarks: OpenRouter `/api/v1/models` → Artificial Analysis intelligence/coding/agentic indices (matched by ID, `:free` falls back to base ID).
  - Curation: Hermes `model-catalog.json` (56/57 curated IDs present on Nous).
  - Auto-pool = curated IDs + their `:free` variants. `:batch` (half price; user reports interactive chat works via Nous Portal, but not verified through the router and not auto-pooled) and region-pinned `:US` variants are explicit-only.
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

## Verified on host (2026-10-23)

- **Real Nous inference through the router works.** A live Hermes Telegram session runs on `/model custom:oracle-router:oracle/auto`; Hermes leaks the provider prefix into the model name, which the router now normalizes (`normalize_model`). Fix landed because the raw form previously returned `Unknown model`.
- Router health (host): 391 routable models, registry fresh; `hermes proxy` Nous adapter ready.
- `/v1/models` advertises only the 5 virtual profiles (picker stays clean); raw ids remain routable by explicit name, full catalog at `/v1/models/profiles`. Verified live on host.
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

## Offline measurement vs xRouteBench (2026-10-23, zero model calls)

`scripts/bench/xroutebench_keyword_tier.py` replays the **precomputed** xRouteBench `llmrouter_generic` test split
(3,729 queries × 18 models, HF `ulab-ai/xRouteBench`) against our `keyword_tier`. Findings (classifier only; the
18-model pool is not our Nous pool, queries are benchmark-style, not chat traffic):
- Reference: best fixed model 0.805, per-query oracle 0.929.
- Keyword tiers separate difficulty only weakly: mean perf over all models is tier1 0.647, tier2 0.518, **tier3 0.691** (n=59).
  Tier 2 is harder than tier 1, but tier 3 ("architecture/design/analysis") is *not* harder, so the tier-3 keywords are not a reliable hardness signal.
- 78% of queries land in tier 1, so the keyword guess alone would send most traffic to the cheapest band; the learned per-bucket floors and escalation are what protect quality, not the classifier.
- Not shown: end-to-end router score (our router starts at a tier floor and escalates, it does not hard-route). Next step if wanted: replay the full `plan()` logic on this data.

### Diagnosis of the tier-3 result (same data) — decision: keyword lists unchanged
- Tier-3 hits are 27/59 `mmlu`, 14 `arc_challenge`, 13 `mmlu_pro`: multiple-choice questions that merely *mention* "security"/"design". That is a benchmark artifact, so it does not show that real "refactor this architecture" chat requests are easy. Retuning keywords on it would overfit the wrong distribution.
- Tier 2 keywords (`code`, `python`, `function`, `test`) do mark harder queries (mean ease ≈0.50 vs 0.62 overall); `regex` is very hard (0.01, n=16).
- Prompt length correlates with difficulty (r = −0.265), but the learner bucket already includes size (`s/m/l`), so length is covered without a classifier change.
- Real evidence must come from our own traffic: `GET /v1/router/learning` floors per bucket. Revisit after a few hundred requests, not before.
