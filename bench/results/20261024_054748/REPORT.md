# Benchmark report

## Scenario `static`

| target | success | warm fetch ms median [95% CI] | peak PSS MiB | cold start ms | vs baseline (latency) |
|---|---|---|---|---|---|
| chrome-cft | 100% | 100.8 [99.9–102.1] | 301.3 [294.8–305.8] | 341.6 [340.5–351.7] | 0.4× |
| chrome-headless-shell | 100% | 41.0 [40.6–42.1] | 86.8 [84.6–87.5] | 237.5 [234.2–247.4] | baseline |
| firefox-pw | 100% | 163.6 [161.4–165.6] | 502.2 [498.9–508.9] | 422.1 [415.8–425.5] | 0.3× |
| lightpanda | 100% | 18.5 [17.9–20.3] | 17.2 [16.8–17.3] | 230.6 [228.3–233.7] | 2.2× |
| playwright-chromium | 100% | 43.1 [42.5–43.5] | 172.3 [171.4–173.6] | 251.5 [237.5–254.9] | 1.0× |

---
Run on 13th Gen Intel(R) Core(TM) i5-13420H (12 cores), kernel 7.0.0-38-generic, load 0.66, git 5a77730, 2026-10-24T02:47:48.392270+00:00.
Method: each cell = independent lifecycles (fresh process); the sample unit is the per-lifecycle median of warm fetches; CIs are 95% bootstrap; a ratio is shown only when CIs do not overlap (n>=10 lifecycles). Latency compares only successful fetches; success rate is reported beside it.