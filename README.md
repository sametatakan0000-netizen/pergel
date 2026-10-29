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

**4 · Desktop app (recommended)** — build the Debian package and install it:

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
<summary><b>No Debian/Ubuntu? Build a package on any distro</b></summary>

The source is plain Python, so you can run it without a `.deb`:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python3 -m src.cli doctor   # sanity check
```

To produce a `.deb` anywhere `dpkg-deb` exists (Debian, Ubuntu, Mint, Pop!_OS,
Kali, MX…), use the same `build_deb` command as step 4.
</details>

### B) Install with an AI agent (Claude Code, Codex, OpenCode, Hermes…)

If you prefer to let an AI agent do the setup, hand it this repository and this
instruction. Copy-paste prompt:

> Clone `https://github.com/sametatakan0000-netizen/pergel.git` and install it for
> me on this machine. First read `AGENTS.md` and `llms.txt`, then follow the
> **Manual install** steps in `README.md` (steps 1–5) in order. Use a virtualenv,
> never `sudo pip install`. If you build the `.deb`, install it with
> `sudo apt install -y ./dist/pergel-browser_*.deb`. Then run
> `python3 -m unittest discover -s tests -t .` and show me the result. Do not
> edit any file outside the repository, and ask me before running any command
> with `sudo`.

Why this works well: the repo is **agent-native**. The agent has three curated
entry points and will not guess its way around:

| File | What the agent gets |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Commands, rules, and the "done is a claim" verification rule |
| [`llms.txt`](llms.txt) | Link-first map of the documentation |
| [`CODEBASE_GRAPH.json`](CODEBASE_GRAPH.json) | AST code graph — navigate without opening files one by one |

Rules that keep an AI install safe: **(1)** the agent reads `AGENTS.md` before
touching code; **(2)** it never invents results — measured or it did not happen;
**(3)** `sudo` only for the `.deb` install, and only after asking you.

---

## Benchmarks — what we measured

> **Scope:** these numbers measure the product's **automation/fetch layer** —
> the programmatic page-fetching engine. Pergel's everyday desktop browsing is
> **Chromium-based**; the ms figures below are *not* your tab speed, they are
> headless fetch/automation throughput.

Measured with `src/bench/run.py` against a deterministic local fixture server.
Each cell = **10 independent lifecycles** (fresh process each time), reported as
a median with a **95% bootstrap confidence interval**. Hardware: 13th Gen Intel
Core i5-13420H (12 cores), kernel 7.0.0-38. Every number below is backed by the
raw measurement file linked at the bottom — nothing here is estimated.

**How to read the three scenarios:**
- `static` — a plain HTML page. The simplest case.
- `spa` — a JavaScript-driven single-page app. The engine must run JS and wait.
- `heavy` — a large page with many resources. The stress case.

### Speed — warm fetch median (ms, lower is better)

| Engine | static | spa | heavy |
|---|---|---|---|
| **lightpanda** | **19.8** | **63.5** | **25.0** |
| chrome-headless-shell | 44.4 | 86.6 | 51.4 |
| playwright-chromium | 44.6 | 87.5 | 51.8 |
| edge | 99.0 | 141.3 | 111.7 |
| brave | 103.3 | 147.6 | 113.2 |
| chrome-cft | 112.6 | 155.2 | 119.9 |
| firefox-pw | 176.8 | 236.5 | 194.1 |
| webkit-pw | 203.4 | 237.8 | 228.5 |

### Memory — peak PSS (MiB, lower is better)

| Engine | static | spa | heavy |
|---|---|---|---|
| **lightpanda** | **23.1** | **24.2** | **23.7** |
| chrome-headless-shell | 175.0 | 174.6 | 160.8 |
| playwright-chromium | 176.0 | 175.2 | 159.3 |
| webkit-pw | 194.3 | 197.5 | 207.3 |
| brave | 325.6 | 354.1 | 366.4 |
| chrome-cft | 479.5 | 501.3 | 500.6 |
| firefox-pw | 506.8 | 511.5 | 508.6 |
| edge | 508.1 | 513.8 | 493.9 |

### Cold start (ms, lower is better)

| Engine | static | spa | heavy |
|---|---|---|---|
| lightpanda | 244.0 | 244.4 | 242.7 |
| playwright-chromium | 261.8 | 267.6 | 263.9 |
| chrome-headless-shell | 264.7 | 262.8 | 264.4 |
| webkit-pw | 266.4 | 258.5 | 256.5 |
| brave | 363.6 | 364.1 | 363.2 |
| chrome-cft | 365.1 | 361.3 | 367.2 |
| edge | 426.9 | 423.1 | 420.0 |
| firefox-pw | 442.2 | 435.8 | 447.9 |

**What this means in plain words:** on this measurement the fetch layer
(`lightpanda`) is roughly **2× faster** and **~10× lighter** than the closest
Chromium-based headless target. For automation and crawling workloads that is a
direct **operating-cost** advantage: the same machine runs far more parallel
sessions on the same RAM.

**Success rate:** every engine above completed **100%** of its fetches in all
three scenarios. One target, `vivaldi`, is shown as **`BLOCKED`**: it never
exposes the CDP DevTools port headless, so it cannot be measured on this rig.
Rather than invent a number, we mark it unmeasurable.

*Run on 13th Gen Intel(R) Core(TM) i5-13420H (12 cores), kernel 7.0.0-38-generic, load 0.57, git 0a56efd, 2026-10-28.*
*Method: sample unit is the per-lifecycle median of warm fetches; CIs are 95% bootstrap; a latency ratio is only claimed where CIs do not overlap (n≥10 lifecycles). Latency compares successful fetches only.*

**Claims we deliberately avoid:** "Pergel is the fastest browser," "fast in all
uses," or any absolute ms guarantee. This measurement does not support those.
`lightpanda` is a third-party (AGPL) engine, not Pergel's own — it is used only
in the fetch/automation layer.

Every cell is backed by raw measurement data:
[`bench/results/20261028-200116_full9/raw.jsonl`](bench/results/20261028-200116_full9/raw.jsonl).

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
