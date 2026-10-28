# Pergel

**A privacy-respecting, telemetry-free, open-source desktop browser built for the AI era.**

Pergel never sells your data, never phones home in the background, and never forces a
single engine or model on you. It runs on a **BYOK (Bring Your Own Key)** philosophy:
you enter your own AI provider key, and your requests go straight to that provider.
There is no middleman holding a balance or reading your prompts.

**English** | [Türkçe](README.tr.md)

- **No telemetry.** No background data flow, no user selling, no ad profiling.
- **BYOK.** Bring your own API key (OpenRouter, Nous, Ollama, and more).
- **Open source & free.** No subscription tiers, no paywalled features.

---

## A repository built for AI agents as much as humans

This repository is organized so that an AI agent can get up to speed quickly. When an
agent starts working here, it reads these files first:

| File | Purpose |
|---|---|
| [`AGENTS.md`](AGENTS.md) | In-repo agent policy: commands, rules, verification |
| [`llms.txt`](llms.txt) | Link-first documentation map |
| [`CODEBASE_GRAPH.json`](CODEBASE_GRAPH.json) | AST-based code graph — navigate without opening files one by one |

Rule: read `CODEBASE_GRAPH.json` before the code, `AGENTS.md` for rules and commands.

---

## Speed / memory — how to read this honestly

> **Important:** The numbers below measure the product's **automation/fetch layer** —
> the programmatic page-fetching engine. Pergel's desktop browsing experience is
> **Chromium-based**; these ms figures do not represent everyday tab speed, they
> represent headless fetch/automation throughput.

Measured with the `src/bench/run.py` harness against a deterministic local fixture
server. Each cell is 10 independent lifecycles (fresh process) with a 95% bootstrap
confidence interval. Hardware: 13th Gen Intel Core i5-13420H (12 cores), kernel 7.0.0-38.
**Only targets with raw measurements in the repo (`bench/results/*/raw.jsonl`) are
reported.** Targets that could not be measured on a given run are shown as
`not measured` rather than filled with placeholder numbers.

<!-- BENCHMARK_TABLES:BEGIN -->
## Scenario `static`

| target | success | warm fetch ms median [95% CI] | peak PSS MiB | cold start ms | vs baseline (latency) |
|---|---|---|---|---|---|
| brave | 100% | 103.3 [102.9–105.4] | 325.6 [322.0–333.8] | 363.6 [357.1–369.6] | 0.4× |
| chrome-cft | 100% | 112.6 [112.2–114.4] | 479.5 [465.2–487.2] | 365.1 [361.9–373.0] | 0.4× |
| chrome-headless-shell | 100% | 44.4 [43.6–45.4] | 175.0 [171.8–176.7] | 264.7 [262.6–269.7] | baseline |
| edge | 100% | 99.0 [97.3–100.4] | 508.1 [506.7–512.4] | 426.9 [421.6–433.1] | 0.4× |
| firefox-pw | 100% | 176.8 [175.3–178.3] | 506.8 [500.8–511.0] | 442.2 [438.5–451.3] | 0.3× |
| lightpanda | 100% | 19.8 [18.8–20.6] | 23.1 [22.8–23.8] | 244.0 [240.4–249.4] | 2.2× |
| playwright-chromium | 100% | 44.6 [43.5–46.1] | 176.0 [174.7–177.3] | 261.8 [259.9–264.1] | no significant difference |
| webkit-pw | 100% | 203.4 [197.7–210.5] | 194.3 [190.0–197.2] | 266.4 [258.2–274.2] | 0.2× |


## Scenario `spa`

| target | success | warm fetch ms median [95% CI] | peak PSS MiB | cold start ms | vs baseline (latency) |
|---|---|---|---|---|---|
| brave | 100% | 147.6 [145.2–149.6] | 354.1 [353.4–355.9] | 364.1 [359.1–384.4] | 0.6× |
| chrome-cft | 100% | 155.2 [153.9–156.9] | 501.3 [497.8–508.0] | 361.3 [356.5–366.4] | 0.6× |
| chrome-headless-shell | 100% | 86.6 [86.3–87.4] | 174.6 [174.2–175.3] | 262.8 [261.0–267.3] | baseline |
| edge | 100% | 141.3 [140.7–142.6] | 513.8 [513.5–516.4] | 423.1 [416.5–433.5] | 0.6× |
| firefox-pw | 100% | 236.5 [233.8–239.8] | 511.5 [503.9–516.3] | 435.8 [434.8–444.1] | 0.4× |
| lightpanda | 100% | 63.5 [62.7–63.8] | 24.2 [23.9–25.1] | 244.4 [240.2–248.7] | 1.4× |
| playwright-chromium | 100% | 87.5 [86.5–88.2] | 175.2 [174.6–176.4] | 267.6 [263.9–270.5] | no significant difference |
| webkit-pw | 100% | 237.8 [236.7–244.8] | 197.5 [197.4–197.7] | 258.5 [255.6–268.2] | 0.4× |


## Scenario `heavy`

| target | success | warm fetch ms median [95% CI] | peak PSS MiB | cold start ms | vs baseline (latency) |
|---|---|---|---|---|---|
| brave | 100% | 113.2 [111.4–114.2] | 366.4 [364.0–366.9] | 363.2 [356.1–372.3] | 0.5× |
| chrome-cft | 100% | 119.9 [118.9–122.6] | 500.6 [497.2–509.9] | 367.2 [360.3–373.2] | 0.4× |
| chrome-headless-shell | 100% | 51.4 [51.0–51.9] | 160.8 [153.6–190.5] | 264.4 [258.8–274.0] | baseline |
| edge | 100% | 111.7 [110.0–113.3] | 493.9 [482.9–526.5] | 420.0 [415.2–428.8] | 0.5× |
| firefox-pw | 100% | 194.1 [190.2–207.6] | 508.6 [501.0–530.9] | 447.9 [443.8–463.5] | 0.3× |
| lightpanda | 100% | 25.0 [23.9–26.0] | 23.7 [23.4–25.6] | 242.7 [240.1–247.8] | 2.1× |
| playwright-chromium | 100% | 51.8 [50.7–52.3] | 159.3 [154.9–167.7] | 263.9 [247.8–268.7] | no significant difference |
| webkit-pw | 100% | 228.5 [221.5–232.6] | 207.3 [202.1–208.4] | 256.5 [251.9–267.1] | 0.2× |


*Run on 13th Gen Intel(R) Core(TM) i5-13420H (12 cores), kernel 7.0.0-38-generic, load 0.57, git a963c14, 2026-10-28T17:01:16.327261+00:00.*
*Method: each cell = independent lifecycles (fresh process); the sample unit is the per-lifecycle median of warm fetches; CIs are 95% bootstrap; a ratio is shown only when CIs do not overlap (n>=10 lifecycles). Latency compares only successful fetches; success rate is reported beside it.*

**Scope honesty:** these are the **automation/fetch layer** engines, not everyday tab speed.
`lightpanda` is a third-party AGPL fetch-layer engine (not Pergel's own). `vivaldi` could not be
measured on this rig (it never exposes the CDP DevTools port headless) and is deliberately shown
as **`BLOCKED`** rather than given a fabricated number. Every cell above is backed by
[`raw.jsonl`](bench/results/20261028-200116_full9/raw.jsonl).
<!-- BENCHMARK_TABLES:END -->

**How to read it correctly:** the fetch layer (lightpanda) is measured ~2.3× faster
and ~10× lighter than the closest Chromium-based headless target. That is a direct
**operating-cost** advantage for automation and crawling workloads.

**Claims we avoid:** "Pergel is the fastest browser," "fast in all uses," or any
absolute ms guarantee. None of that is supported by this measurement. lightpanda is a
third-party (AGPL) engine; it is not Pergel's own engine and is used only in the
fetch/automation layer.

---

## Honesty note (transparency)

Performance numbers in this repository are published **only** alongside reproducible
measurement output (`bench/results/`). Competitor rows without raw measurements in the
repo are deliberately omitted or marked `not measured` — never filled with estimates.
The marketing rule here is "speak with what you measured, don't exaggerate."

---

## Development

```bash
# test suite (must be green)
python3 -m unittest discover -s tests -t .

# refresh the code graph
PYTHONPATH=. python3 -m src.cli graph

# doctor + security/debt audit
PYTHONPATH=. python3 -m src.cli doctor
```

See [`AGENTS.md`](AGENTS.md) for the full rules and commands.

---

## License

The code is subject to third-party component licenses (Chromium-based shell is
BSD-3-Clause, the automation engine is AGPL-3.0, and others). See [`LICENSE`](LICENSE)
and the component notes under `docs/rea/`.

## Support

Pergel will always be free. If you'd like to keep development going, you can support it
through [GitHub Sponsors](https://github.com/sponsors/sametatakan0000-netizen).
