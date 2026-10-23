# Product status — browser engine SaaS (verified slices only)

Run tests: `.venv/bin/python -m unittest discover -s tests -t .` (94 pass; system python skips the trafilatura test).

## Verified real (2026-10-23, host)
- Search: SearXNG in Docker (`searxng`, 127.0.0.1:8888, `restart unless-stopped`, config `~/.local/share/searxng/settings.yml`). Fan-out returned 10 deduped cited sources for a TR/EN query.
- Fetch+extract: real fetch of lightpanda.io via the HTTP driver -> 6007 chars clean markdown; github.com page -> 15807 chars.
- Policy: robots.txt, 2 MB cap, content-type guard, SSRF guard, policy blocks never escalate.

## Not real yet
- All three engine tiers are the same plain-HTTP fetch. No JS rendering: lightpanda/chromium binaries not installed.
- HAR/XHR discovery regex gives false positives (favicon manifest.json, trailing `\`) — fix pending.
- Fan-out subquery split is a crude regex (TR/EN conjunctions or half-split).
- No auth/rate limiting on the SaaS API (loopback only).
