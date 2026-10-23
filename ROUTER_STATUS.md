# Router status — prototype, not production

The previous claim that all Nous Portal models and fine-tuning parameters are live and adaptive was false. This repository does **not** modify the current Hermes gateway or its default model.

## Verified behavior

- `python3 -m src.cli serve` starts a loopback-only OpenAI-compatible router at `127.0.0.1:8090/v1`. It forwards `/v1/chat/completions` requests, including `messages`, `tools`, and SSE streaming, to a separately running `hermes proxy start` at `127.0.0.1:8645/v1`. The router does not mint or store Portal credentials.
- If upstream is absent, chat returns 502 (never a fabricated success); upstream errors propagate. `/v1/health` reports `degraded` until upstream `/v1/models` responds. The old `/v1/router/complete` fake path is disabled (501).
- The route is sticky per session **only in this process's memory**; restarts lose affinity. Use the `x-hermes-session-id` header. The old scoring algorithm remains a prototype; chat completions do not self-validate or write fake success signals.
- `python3 -m src.cli refresh-catalog --db-path /path/router.db` reads the public Hermes curated model catalog and persists *new IDs* in SQLite. When serving, a background thread refreshes every 20 minutes. Catalog membership does not prove availability in your account or capability.
- Exported `MODEL_PROFILES.json` marks metadata as `unverified`. Most persona, price, tier, context length, vision, and tools flags were guessed by the previous implementation. New catalog-only IDs have unknown pricing (`-1` sentinel) and are excluded from automatic route selection.

## Not verified / known limitations

- The Nous OAuth subscription proxy was not available in the Docker terminal environment; **no paid real inference call has been tested**. The integration tests use a local HTTP fixture, not Nous.
- `oracle/auto` routes by a rudimentary keyword/tier heuristic; it is **not** a benchmarked SOTA optimizer. Fine-tuning values in `get_adaptive_tuning()` are metadata only and are **not transmitted to upstream**. Provider-specific reasoning and temperature are not safe to assume supported.
- Session sticky state is not persisted; model switches after restart may break prompt caching. There is no robust independent answer oracle, latency/cost telemetry, quality benchmark, rollback, or account-scoped capability matrix.
- Model profile membership comes from a 57-entry curated list plus manually written guesses, **not all 346 Portal models**. `/v1/models` is not a verified account-scoped provider model list.
- Other SaaS demo endpoints (browse/search/watchdog) still have mock or simplified behavior. Do not use them as production evidence.

## Safe verification sequence (on the Hermes host, not the agent's Docker terminal backend)

1. Check `hermes portal info` and `hermes proxy status`; run `hermes proxy start` bound to loopback under a managed service/terminal. Check `curl -f http://127.0.0.1:8645/v1/models`.
2. Start `python3 -m src.cli serve --db-dir /path/to/persistent/project` **in the same network namespace**; check `curl -f http://127.0.0.1:8090/v1/health`. Confirm `upstream_ready: true`.
3. Send a non-sensitive low-cost test request through `/v1/chat/completions` and compare the returned `id`, `model`, `usage`, and output with the Portal proxy. Exercise streaming + tool calls separately; inspect Nous billing.
4. Only after verification, review the five `providers.oracle-router` commands in `scripts/hermes_full_optimize_commands.sh` and opt in with `ORACLE_ROUTER_APPLY=1`. **Do not change `model.provider` or `model.default`** until production-grade eligibility and session-affinity checks exist. The script's default is dry-run.

Tests: `python3 -m unittest discover -s tests -t . -v`; status: `python3 -m src.cli doctor` (returns `PROTOTYPE`, not `READY`).
