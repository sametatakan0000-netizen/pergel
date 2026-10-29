# Pergel

**Open-source, privacy-first browser with a real AI mode — built for people *and* AI agents.**

Pergel is two things in one project: a **desktop browser** you can use every day (Chromium
engine, ad & tracker blocking, 8 languages), and a **lightweight browsing engine + API** that AI
agents use to read the web fast and cheaply.

Privacy is the product, not a footnote. Pergel never sells your data, never phones home in the
background, and never forces a single engine or model on you. It runs on a **BYOK (Bring Your
Own Key)** philosophy: you enter your own AI provider key, and your requests go straight to that
provider. There is no middleman holding a balance or reading your prompts.

**English** | [Türkçe](README.tr.md)

- **No telemetry.** No background data flow, no data selling, no ad profiling. No account.
- **BYOK.** Bring your own API key (OpenRouter, Nous, Ollama, and more).
- **Open source & free.** No subscription tiers, no paywalled features — now and always.

---

## Why this exists

The project started from one observation, backed by market research kept in this repo
(`docs/product/market-landscape_2026-10-26.md`, `docs/rea/ai-browsers.md`):

**AI's biggest weakness is surfing the web — not chatting.** When an AI agent browses, it burns
tokens on messy DOM, guesses at page structure, and pays full price for heavy pages it barely
needed. Meanwhile the "AI browser" market is mostly an answer box bolted onto a search engine,
or a $20/month agent running on someone else's cloud, on someone else's terms.

Four things we set out to fix from day one:

1. **AI should surf well, cheaply.** A multi-engine ladder lets a cheap page stay cheap —
   a direct *running-cost* advantage (see the benchmarks below).
2. **AI mode is not AI search.** The difference is real, and it's the point — next section.
3. **Privacy, non-negotiably.** No data sales, no telemetry, no background sync. Researched
   against what incumbents actually collect (`docs/rea/security_posture_evaluation_2026-10.md`).
4. **Honesty over hype.** Every number here is backed by a raw measurement file in this repo.
   What we didn't measure, we say so.

---

## AI mode vs. classic AI search — what's actually different

Market research (`docs/product/market-landscape_2026-10-26.md`) puts AI web access into four
categories: **(A)** read/Markdown APIs, **(B)** search + content, **(C)** remote browser / browser
agent, **(D)** agentic-native surfaces (WebMCP). Classic "AI search" lives in **B** — it answers,
and you either trust it or you don't.

| | Classic AI search | Pergel's AI mode |
|---|---|---|
| Output | One generated answer | Sub-queries + **inline citations** you can click |
| Grounding | Model memory + snippets | Real fetched pages, cleaned |
| Cost | Full price on heavy pages | Cheap page stays cheap (engine ladder) |
| Transparency | "Trust me" | Every claim points at a source |

What that looks like in the product:

- **Query Fan-Out** (`/v1/search/fanout`) — one question becomes several sub-queries, results
  gathered and answered **with inline citations**. Grounded answers, not vibes.
- **Engine ladder** — a light page goes to the lightweight fetch engine; a JS-heavy page
  escalates to full Chromium. You don't pay Chromium prices for a static page.
- **Built-in blocking** — a rule engine with **92k+ rules and no MV3 quota**. Chrome's extension
  store crippled ad-blockers when MV2 was removed; Pergel blocks natively.
- **Agent-native interface** — REST API + **MCP server** (`src/mcp_server.py`) + CLI + CDP.
  An AI assistant drives Pergel the same way a person does.

One more thing worth knowing: **prompt injection is unsolved in 2026** (hidden page instructions
tricking agents — `docs/rea/ai-browsers.md`). Our answer, designed in from the start: separate
profile isolation + a confirmation gate + a content-instruction filter.

---

## A repository built for AI agents as much as humans

This repository is organized so that an AI agent can get up to speed quickly. When an agent
starts working here, it reads these files first:

| File | Purpose |
|---|---|
| [`AGENTS.md`](AGENTS.md) | In-repo agent policy: commands, rules, verification |
| [`llms.txt`](llms.txt) | Link-first documentation map |
| [`CODEBASE_GRAPH.json`](CODEBASE_GRAPH.json) | AST-based code graph — navigate without opening files one by one |

Rule: read `CODEBASE_GRAPH.json` before the code, `AGENTS.md` for rules and commands.

---

## What's in the box

| Surface | What it is | For whom |
|---|---|---|
| **Desktop browser** | Chromium-based, blocking built in, 8 languages (incl. RTL), real window mode | people |
| **REST API** | `/v1/jobs/browse`, `/v1/search/fanout`, `/v1/chat/completions`, router endpoints | integrators |
| **MCP server** | `browse_url`, `search_fanout`, `list_models`, `router_health` | AI assistants |
| **CLI** | `pergel` — doctor, browse, package, graph | people + agents |
| **Model router** | 425-model registry from public data, deterministic cost/quality routing, BYOK | everyone |

---

## How it works

**Engine ladder.** Fetch a page cheaply; escalate to a full browser only when the page needs it:

`lightweight fetch engine (lightpanda) → Chromium (Playwright/CDP)`

**Security layers (wired into the fetch path, fail-closed):**
- SSRF guard: resolve-once, validate-all, connect-to-validated-IP; DNS-rebinding + redirect
  re-validation (IP pinning).
- Network namespace isolation for Chromium (fail-closed) + egress proxy relay with per-hop checks.
- Content rule engine (92k+ rules) enforced at the CDP layer.

**Smart model routing.** A LiveRouter + registry built from **public, key-less data** (Nous Portal
billed prices x OpenRouter benchmarks x Hermes catalog) — a deterministic cost/quality policy.
No model is ever called to profile it.

**Everything is testable and deterministic** — 700+ unit tests, hermetic fixtures, no live-network
flakes in the suite.

---

## Who it competes with

Researched October 2026 (sources in `docs/rea/ai-browsers.md` and
`docs/product/market-landscape_2026-10-26.md`). Trademarks belong to their owners; this is
descriptive market context, not a benchmark.

| Product | Engine | Agent | Platforms | Price |
|---|---|---|---|---|
| Perplexity Comet | Chromium | yes (quota) | Win/mac/iOS/Android | free; Pro $20 |
| ChatGPT Atlas *(shut down 08/2026)* | Chromium | yes | macOS | — |
| Chrome + Gemini | Chromium | yes (US, paid) | all | $19.99+ |
| Edge + Copilot | Chromium | yes (US) | all | free / M365 |
| Opera Neon | Chromium | yes ($19.90) | Win/mac | paid |
| Fellou / Genspark / BrowserOS | Chromium | yes | Win/mac | free–$25 |
| **Pergel** | Chromium + light fetch engine | yes (local, BYOM) | **Linux pkg; cross-platform core** | **free forever** |

**Where we win (honest):** a fast, light fetch layer that's cheap to run at scale; blocking that
survives MV3; citations instead of vibes; zero telemetry; a clean automation surface (stable CDP).
**Where we lose (honest):** no ready-made user base, no first-party model, no extension-store
parity yet. The full analysis, wins *and* losses, is in
[`docs/rea/positioning-synthesis.md`](docs/rea/positioning-synthesis.md).

---

## Benchmarks — what we measured

> **Scope:** these numbers measure Pergel's **automation/fetch layer** — the programmatic
> page-fetching engine. Pergel's everyday desktop browsing is **Chromium-based**; the ms figures
> below are headless fetch/automation speed, not your tab-switching speed.

Measured with `src/bench/run.py` against a deterministic local fixture server. Each cell is
**10 independent lifecycles** (fresh process each time), reported as a median with a **95%
bootstrap confidence interval**. Hardware: 13th Gen Intel Core i5-13420H (12 cores), kernel
7.0.0-38. Every number below is backed by the raw measurement file linked at the bottom —
nothing here is estimated.

The rows named **Pergel** are Pergel's own engine layers; the `*(ref)*` rows are independent
browsers included only as comparison references.

**How to read the three scenarios:**
- `static` — a plain HTML page. The simplest case.
- `spa` — a JavaScript-driven single-page app. The engine must run JS and wait.
- `heavy` — a large page with many resources. The stress case.

### Speed — warm fetch median (ms, lower is better)

| Engine | static | spa | heavy |
|---|---|---|---|
| **Pergel · fetch engine** (lightpanda) | **19.8** | **63.5** | **25.0** |
| **Pergel · desktop engine** (Chromium) | 112.6 | 155.2 | 119.9 |
| chrome-headless-shell *(ref)* | 44.4 | 86.6 | 51.4 |
| playwright-chromium *(ref)* | 44.6 | 87.5 | 51.8 |
| edge *(ref)* | 99.0 | 141.3 | 111.7 |
| brave *(ref)* | 103.3 | 147.6 | 113.2 |
| firefox-pw *(ref)* | 176.8 | 236.5 | 194.1 |
| webkit-pw *(ref)* | 203.4 | 237.8 | 228.5 |

### Memory — peak PSS (MiB, lower is better)

| Engine | static | spa | heavy |
|---|---|---|---|
| **Pergel · fetch engine** (lightpanda) | **23.1** | **24.2** | **23.7** |
| **Pergel · desktop engine** (Chromium) | 479.5 | 501.3 | 500.6 |
| chrome-headless-shell *(ref)* | 175.0 | 174.6 | 160.8 |
| playwright-chromium *(ref)* | 176.0 | 175.2 | 159.3 |
| webkit-pw *(ref)* | 194.3 | 197.5 | 207.3 |
| brave *(ref)* | 325.6 | 354.1 | 366.4 |
| firefox-pw *(ref)* | 506.8 | 511.5 | 508.6 |
| edge *(ref)* | 508.1 | 513.8 | 493.9 |

### Cold start (ms, lower is better)

| Engine | static | spa | heavy |
|---|---|---|---|
| **Pergel · fetch engine** (lightpanda) | 244.0 | 244.4 | 242.7 |
| **Pergel · desktop engine** (Chromium) | 365.1 | 361.3 | 367.2 |
| playwright-chromium *(ref)* | 261.8 | 267.6 | 263.9 |
| chrome-headless-shell *(ref)* | 264.7 | 262.8 | 264.4 |
| webkit-pw *(ref)* | 266.4 | 258.5 | 256.5 |
| brave *(ref)* | 363.6 | 364.1 | 363.2 |
| edge *(ref)* | 426.9 | 423.1 | 420.0 |
| firefox-pw *(ref)* | 442.2 | 435.8 | 447.9 |

**What this means in plain words:** Pergel's fetch layer (lightpanda) is roughly **2x faster**
and **~10x lighter** than the closest Chromium-based headless target. For automation and crawling
workloads that is a direct **operating-cost** advantage: the same machine, the same RAM, carries
far more parallel sessions. (The desktop engine is full Chromium — that's what you browse in
daily; its memory cost is what a real browser pays.)

**Success rate:** every engine above completed **100%** of its fetches in all three scenarios.
One target, `vivaldi`, is shown as **`BLOCKED`**: it never exposes the CDP DevTools port headless,
so it cannot be measured on this rig. Rather than invent a number, we mark it unmeasurable.

*Run on 13th Gen Intel(R) Core(TM) i5-13420H (12 cores), kernel 7.0.0-38-generic, load 0.57, git `0a56efd`, 2026-10-28.*
*Method: sample unit is the per-lifecycle median of warm fetches; CIs are 95% bootstrap; a latency ratio is only claimed where CIs do not overlap (n>=10 lifecycles). Latency compares successful fetches only.*

**Claims we deliberately avoid:** "Pergel is the fastest browser," "fast in all uses," or any
absolute ms guarantee. This measurement does not support those. `lightpanda` is a third-party
(AGPL) engine used as Pergel's fetch/automation layer — not a claim that it is Pergel's own
rendering engine.

Every cell is backed by raw measurement data:
[`bench/results/20261028-200116_full9/raw.jsonl`](bench/results/20261028-200116_full9/raw.jsonl).

---

## Platform support

Pergel's core is plain Python 3.10+ with no platform-specific code — it runs wherever Python
runs. Packaging is what's platform-specific.

| Platform | Core (engine, router, API, MCP, CLI) | Desktop package | Lightweight fetch engine |
|---|---|---|---|
| **Debian / Ubuntu** (and derivatives) | yes | yes `.deb` + app menu | yes |
| Other Linux | yes | run from source | yes |
| macOS | yes | run from source | yes |
| Windows | yes | run from source | no (falls back to Chromium) |

On Windows the engine ladder automatically falls back to Chromium — nothing breaks, you just
don't get the light engine.

---

## Installation

Two supported paths. Pick the one that fits you — both are first-class.

### A) Manual install (for people)

**1 · Get the code**

```bash
git clone https://github.com/sametatakan0000-netizen/pergel.git
cd pergel
```

**2 · Requirements** — Python **3.10+** and a Chromium-family browser.

```bash
sudo apt update
sudo apt install -y python3 python3-venv chromium-browser   # or google-chrome-stable
```

**3 · Python dependencies**

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

**4 · Desktop app (recommended on Debian/Ubuntu)** — build the Debian package and install it:

```bash
PYTHONPATH=. python3 -c "from src.brand.package import build_deb; print(build_deb('dist'))"
sudo apt install -y ./dist/pergel-browser_*.deb
```

This installs `pergel` to `/usr/bin/pergel` and a menu entry. Then just launch
**Pergel** from your application menu, or run `pergel` in a terminal.

**5 · Verify it works**

```bash
pergel --help                       # the app launches
python3 -m unittest discover -s tests -t .   # the suite is green
```

<details>
<summary><b>Not Debian/Ubuntu (macOS, Windows, other distros)? Run from source</b></summary>

The source is plain Python, so you can run it without a `.deb`:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python3 -m src.cli doctor   # sanity check
```

On Windows (PowerShell): `py -3 -m venv .venv`, then `.venv\Scripts\Activate.ps1`, then the same
`pip install`. To produce a `.deb` anywhere `dpkg-deb` exists (Debian, Ubuntu, Mint, Pop!_OS,
Kali, MX...), use the same `build_deb` command as step 4.
</details>

### B) Install with an AI agent (Claude Code, Codex, OpenCode, Hermes...)

If you prefer to let an AI agent do the setup, hand it this repository and this instruction.
Copy-paste prompt:

> Clone `https://github.com/sametatakan0000-netizen/pergel.git` and install it for me on this
> machine. First read `AGENTS.md` and `llms.txt`, then follow the **Manual install** steps in
> `README.md` (steps 1-5) in order. Use a virtualenv, never `sudo pip install`. If you build the
> `.deb`, install it with `sudo apt install -y ./dist/pergel-browser_*.deb`. Then run
> `python3 -m unittest discover -s tests -t .` and show me the result. Do not edit any file
> outside the repository, and ask me before running any command with `sudo`.

Why this works well: the repo is **agent-native**. The agent has three curated entry points and
will not guess its way around. The three rules that keep an AI install safe: **(1)** the agent
reads `AGENTS.md` before touching code; **(2)** it never invents results — measured or it did not
happen; **(3)** `sudo` only for the `.deb` install, and only after asking you.

---

## How we got here (project history)

Built openly and continuously — real work, in order (full list: `git log`):

- **Research-first start** — browser-engine SOTA survey and a written architecture decision
  (`docs/research/browser_engine_sota_2026-10.md`): don't build "another scraper"; differentiate
  on routing, cost, and citations.
- **Three-engine test campaign** — Chrome-CFT + Chromium + Lightpanda, 138 fresh processes,
  100% verification rate.
- **Competitive benchmark** — bootstrap confidence intervals, honest `BLOCKED` marking for
  Vivaldi.
- **Security layer** — Chromium in a network namespace (fail-closed), SSRF guard, egress proxy
  relay with per-hop redirect checks.
- **Extension platform** — MV3 rule surface + isolated extension host, enforced end-to-end at
  the CDP layer.
- **Platform adapters** — structured-API-first fetch: oEmbed (YouTube/Vimeo/Instagram), YouTube
  transcripts, RSS/Atom + sitemap fallback, Wayback Machine, Reddit OAuth.
- **Deeper hardening** — DNS-rebinding defence, IP pinning, redirect re-validation, live TLS
  verification (real certificate + handshake).
- **AI mode** — query fan-out + citations, REST API, MCP server, and the LiveRouter + model
  registry (public data, deterministic policy).
- **Global-first** — 8 languages, RTL, accessibility.
- **Identity** — a full rebrand (Vane -> Pergel), icons, `.deb` desktop package.

---

## What Pergel does *not* have yet

1. **Web UI** (`/ui/` control panel) — not built yet.
2. **Session record/replay, Live View** — not yet.
3. **WebMCP** — not yet (needs Chromium 146+).
4. **Windows/macOS native packaging** — run from source works; installers not built.

We do **not** build stealth/anti-detection to bypass paywalls or bot walls; our security
work is defence (SSRF/egress/privacy), never evasion.

---

## Docs & deep research

Everything above is grounded in documents kept in this repo:

- [`docs/rea/positioning-synthesis.md`](docs/rea/positioning-synthesis.md) — where Pergel wins
  and loses (patch-lag table, CDP surface, supply-chain).
- [`docs/rea/ai-browsers.md`](docs/rea/ai-browsers.md) — the 2026 AI-browser market and the
  prompt-injection problem.
- [`docs/product/market-landscape_2026-10-26.md`](docs/product/market-landscape_2026-10-26.md) —
  the four ways AI agents access the web, with competitor pricing.
- [`docs/research/browser_engine_sota_2026-10.md`](docs/research/browser_engine_sota_2026-10.md) —
  the architecture decision table.

---

## Honesty note (transparency)

Performance numbers in this repository are published **only** alongside reproducible measurement
output (`bench/results/`). Competitor rows without raw measurements in the repo are deliberately
omitted or marked `BLOCKED` — never filled with estimates. The marketing rule here is "speak with
what you measured, don't exaggerate."

What Pergel is not: a finished commercial browser. It is an actively developed, already useful
open-source browser + engine. The desktop experience is Chromium-based; the automation/fetch
layer is what the benchmarks above measure.

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

The code is subject to third-party component licenses (Chromium-based shell is BSD-3-Clause, the
automation engine is AGPL-3.0, and others). See [`LICENSE`](LICENSE) and the component notes
under `docs/rea/`. Lightpanda is used as one fetch-engine tier and Chromium via Playwright/CDP —
both are their owners' components, used under their respective licenses.

## Support

Pergel will always be free. If you'd like to keep development going, you can support it through
[GitHub Sponsors](https://github.com/sponsors/sametatakan0000-netizen).

---

*Open source. Privacy-first. Made for humans and agents alike.*
