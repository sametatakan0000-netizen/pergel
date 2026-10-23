# AGENTS.md — AI-Native Browser Engine & Self-Evolving Lab Constitution

## 1. Core Architecture & Directories
- `src/search/query_fanout.py` — Live-Index Query Fan-Out & inline citation grounding (`[N] (url)`).
- `src/router/oracle_router.py` — 3-Tier Dynamic Model Router with Oracle validation & Exponential Half-Life Decay ($w(\Delta t) = 2^{-\Delta t / T_{1/2}}$).
- `src/infra/` — Hermes Agent verified config builder, Self-Healing Watchdog, and HMAC-SHA256 Webhook Dispatcher.
- `src/browser_engine/` — Multi-engine orchestrator & cascading worker (`lightpanda` → `chromium-browser-use` → `camofox` + HAR/XHR API discovery).
- `src/api/` — SQLite WAL Job Store (`job_store.py`) and ThreadingHTTPServer SaaS REST API (`server.py`).
- `src/devtools/` — Senior-Dev Toolbox: AST Codebase Graph (`codebase_graph.py`), RTK/Caveman log compressor & Ponytail debt scanner (`token_and_debt_hygiene.py`), Defensive Security & ToxicSkills quarantine (`security_audit.py`), and 3-Mode Self-Evolution Engine (`self_evolution_engine.py`).
- `src/net_lab/sober_net_diagnostics.py` — Linux Sober (Roblox) & Minecraft socket/MTU/TLS diagnostics.

## 2. Verification & Commands (S-Tier Rule #1: "Done is a Claim — Show the Receipt")
- (`$REPO` = repo root: `~/.hermes/sandboxes/docker/default/home/ai_browser_farm` on host)
- Run full test suite (must pass 100% before and after every change):
  ```bash
  python3 -m unittest discover -s $REPO/tests -t $REPO -v
  ```
- Refresh Codebase Knowledge Graph (`CODEBASE_GRAPH.json`):
  ```bash
  PYTHONPATH=$REPO python3 -m src.cli graph
  ```
- Run full Doctor & Security/Debt Audit:
  ```bash
  PYTHONPATH=$REPO python3 -m src.cli doctor
  ```

## 3. Senior Engineering Rules (Karpathy + Ponytail + RTK + Graphify)
1. **Graph-First Navigation:** Read `$REPO/CODEBASE_GRAPH.json` before opening individual source files to avoid burning context tokens.
2. **YAGNI & Shortcut Debt Ledger (`ponytail`):** Write minimal, zero-bloat code. Any deliberate simplification MUST carry a comment `# shortcut: <current limit>, <when to upgrade>`.
3. **Token & Context Hygiene (`rtk` / `caveman`):** Keep active context well below 200k tokens. Compress noisy CLI outputs via `compress_cli_output`.
4. **ToxicSkills Quarantine (`Snyk` / `Strix`):** Never install an external `SKILL.md` without passing `audit_skill_markdown` first.
5. **Hermes Config Invariant:** Never hand-edit `~/.hermes/config.yaml`; always use `hermes config set KEY VAL`.
