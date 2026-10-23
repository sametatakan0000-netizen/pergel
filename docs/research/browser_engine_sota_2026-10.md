# Browser engine SOTA (web research, 2026-10-23) — decision table

Sources: usestring.ai firecrawl-alternatives (2026-10-19), firecrawl.dev/blog/best-browser-agents (2026-10-21),
wavect.io Lightpanda review (2026-08/09), trafilatura docs (evaluation), bulkmd benchmark (2026-05, 50 pages, single-author),
camoufox.com/stealth, browser-use.com Online-Mind2Web post (self-reported), leaderboard.steel.dev.

| Area | Finding | Decision |
|---|---|---|
| Market | Firecrawl (~177K stars), Crawl4AI (~81K), Crawlee (~25K), Browserbase/Steel (managed), Browser Use (agent). Crowded; differentiation must be routing + cost + citations, not "another scraper". | Differentiate: cascading engine floor per domain + Query Fan-Out with inline citations + HAR/XHR API discovery (all exist in repo). |
| HTML->markdown | Trafilatura: best single tool in Bevendorff 2023 (ROUGE-LSum), ScrapingHub benchmark; outputs markdown directly. Readability is JS-only. Our regex converter is unprincipled. | ADOPT trafilatura (optional dep, regex fallback marked `# shortcut:`). |
| Fast engine | Lightpanda (Zig, V8, CDP; native MCP + agent mode). 9x speed/16x memory claims are vendor numbers; not full Web API coverage -> not a universal Chrome replacement. | Keep as tier 1 with escalation to Chromium on failure (design already matches). Needs binary install. |
| Full engine | Chromium via Playwright/CDP. | Tier 2. |
| Stealth | Camoufox actively developed but "can still be detected" (its own README). Legal/ToS exposure. | DEFER; behind explicit opt-in, robots.txt honored by default. |
| Agent benchmark | Online-Mind2Web is the standard; top scores self-reported with custom judges; WebVoyager considered broken. | Do not claim agent scores. Our metric: extraction fidelity on fixtures + escalation correctness. |
| Interface | MCP is expected surface for agent tools. | Slice 4: MCP/tool wrapper over existing REST job API. |

Caveats: bulkmd and vendor blogs are single-source/marketing; treat as directional.

## Environment (host, probed): Python 3.14.4; NO trafilatura/playwright/httpx; NO lightpanda/chromium on PATH.
