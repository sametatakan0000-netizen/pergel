# Plan: Session cleanup, then target product (AI-Native Browser Engine SaaS)

## Goal
Delete every Hermes session except the current one (no orphans), then start building the target product (browser engine SaaS) on a SOTA-verified, TDD basis.

## Context / assumptions
- Repo: `~/.hermes/sandboxes/docker/default/home/ai_browser_farm` (host path, terminal backend = ssh as `pc`). `$REPO` = that path.
- Router/infra work is done (see `ROUTER_STATUS.md`). Product code is still thin: `src/browser_engine/worker.py` (127 loc, regex HTML->markdown, HAR/XHR endpoint regex), `browser_orchestrator.py` (179 loc, per-domain engine floor in SQLite), `src/search/query_fanout.py` (88 loc), `src/api/{job_store,server}.py` (SaaS REST + router proxy). No lightpanda/chromium binary on PATH (`which` returned nothing) -> engines are currently stubs.
- Current session to KEEP: `20261023_232448_3b0df7d2` (title "[/plan — plan mode]"). Verify the id with `hermes sessions list` right before deleting (it may differ after /new).
- Observed sessions to delete: 9 others (3 `local-*` titled silent-infra-watchdog / self-evolution-ecosystem, 2 untitled `local-*` with workspace `pc`, 5 gateway sessions). Pinned/archived sessions are skipped by default -> must handle explicitly.
- Running gateway (`hermes gateway run`) and `hermes proxy` (port 8645) processes are legit; do NOT kill them.
- User will run slash commands themselves; agent uses CLI equivalents and mentions needed ones only when required.

## Part A — Session cleanup (5 min; mutating, runs only after plan approval)
Cleanup = delete session rows + verify nothing stale (cron-spawned, archived, pinned, orphan child processes).

1. Snapshot (read-only, include archived/pinned):
   `hermes sessions list; hermes sessions pinned; hermes sessions stats`
   Record the KEEP id.
2. Dry-run prune of everything except keep: prune has no "except" flag, so delete by id. Build the list:
   ```bash
   KEEP=20261023_232448_3b0df7d2
   hermes sessions list 2>/dev/null | awk 'NR>2{print $NF}' | grep -v "^$KEEP$" > /tmp/del_ids.txt
   wc -l /tmp/del_ids.txt     # expect 9 (plus any hidden ones)
   ```
3. Unpin/unarchive if any appeared in step 1 (`hermes sessions unpin <id>`), otherwise delete skips them.
4. Delete:
   ```bash
   while read id; do hermes sessions delete --yes "$id"; done < /tmp/del_ids.txt
   ```
5. Sweep leftovers hidden from `list` (archived):
   `hermes sessions prune --older-than 0d --include-archived --dry-run` — the dry-run output must show only KEEP (or nothing); if it lists others, rerun with `--yes`. CHECK the dry-run before `--yes`: it must NOT list the KEEP id (if it does, use per-id deletes only).
6. Orphan check:
   - `hermes sessions list` -> expect exactly 1 row (KEEP).
   - `hermes cron list` -> cron jobs spawn sessions (silent-infra-watchdog, self-evolution). Do NOT delete jobs (user wants continuous self-evolution); just confirm they exist. Ask only if the user wants those cron-created sessions auto-pruned (see open questions).
   - `ps -eo pid,etimes,cmd | grep -E 'hermes|chrom|lightpanda|playwright' | grep -v grep` -> only gateway + proxy + ssh mux expected; any other long-lived child = orphan to report (don't kill without telling).
   - `hermes sessions optimize` (VACUUM, no data change) then `hermes sessions stats` -> 1 session.
7. Report: before/after counts.

## Part B — Target product (SOTA research first, then TDD slices)
Architecture: keep the existing cascading-engine design (lightpanda -> chromium/browser-use -> camofox), turn each stub into a real, tested adapter behind one `Engine` protocol; expose via the existing REST job API; output = clean markdown + cited sources + discovered APIs.

Standing rule: before coding, fresh web research proves the approach is SOTA.

B0. Research (read-only, ~15 min), write findings to `$REPO/docs/research/browser_engine_sota_2026-10.md`:
   - Current state of AI-native browsers/crawl APIs (Firecrawl, Browserbase, Steel, Crawl4AI, browser-use, Stagehand, Lightpanda releases, Camoufox) — features, pricing, benchmarks.
   - HTML->markdown best practice (readability + trafilatura/markdownify vs regex), anti-bot handling, MCP/agent interface expectations.
   - Output: a one-page decision table (adopt / build / skip) and a "gap vs our code" list. Present to user before B1.
B1. Environment probe (read-only): `python3 --version; pip list | grep -Ei 'playwright|trafilatura|markdownify|httpx'; which lightpanda chromium`; decide dependencies with the user (installs are mutating).
B2. Slice 1 — real content extraction (TDD): failing test in `tests/test_browser_worker.py` for an HTML fixture (nav/footer boilerplate, tables, code blocks) -> expect clean markdown; run `python3 -m unittest tests.test_browser_worker -v` (FAIL) -> replace regex converter in `src/browser_engine/worker.py` with chosen library (fallback to current regex on ImportError, with `# shortcut:` note) -> PASS -> commit.
B3. Slice 2 — first real engine adapter (plain HTTP fetch tier, then lightpanda/chromium tier when binary available): test with a local `http.server` fixture (no external network); implement `fetch()` returning `{status, html, engine}`; wire `select_engine`/`record_domain_escalation` on failure (403/empty body -> escalate). Commit.
B4. Slice 3 — end-to-end job: POST job to `src/api/server.py` -> worker -> markdown + HAR API list + fan-out citations; extend `tests/test_e2e_saas_product.py`. Commit.
B5. Slice 4 — agent-facing surface (MCP/tool or OpenAI-style function) per B0 decision. Commit.
B6. After each slice: full suite `python3 -m unittest discover -s $REPO/tests -t $REPO` (must stay 100%), `PYTHONPATH=$REPO python3 -m src.cli graph`, update `ROUTER_STATUS.md`/new `PRODUCT_STATUS.md` with verified claims only.

## Risks / open questions
- Deleting sessions is irreversible (memory/skills persist separately, so learnings survive). Optionally `hermes sessions export` to `~/session_backup.jsonl` first — recommended, 1 command.
- Cron jobs will recreate sessions each run (silent-infra-watchdog). Want a recurring `hermes sessions prune --older-than 2d --source cron` cron? (open question)
- Heavy dependencies (Playwright/chromium ~300 MB) need user approval.
- Anti-bot/legal scope (robots.txt, ToS) must be decided before adding stealth engines (camofox).
