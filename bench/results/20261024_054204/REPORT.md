# Benchmark report

## Scenario `heavy`

| target | success | warm fetch ms median [95% CI] | peak PSS MiB | cold start ms | vs baseline (latency) |
|---|---|---|---|---|---|
| chrome-cft | 100% | 111.1 [109.4–111.5] | 312.4 [304.1–319.1] | 340.9 [334.1–349.7] | 0.4× |
| chrome-headless-shell | 100% | 49.2 [48.8–50.1] | 93.4 [92.4–94.6] | 238.6 [233.7–245.3] | baseline |
| firefox-pw | 100% | 179.4 [177.1–181.9] | 511.7 [506.2–516.8] | 416.8 [410.0–422.4] | 0.3× |
| lightpanda | 100% | 24.0 [23.3–24.9] | 19.2 [18.5–19.3] | 229.6 [226.6–232.7] | 2.1× |
| playwright-chromium | 100% | 49.8 [49.2–51.2] | 180.1 [178.7–180.9] | 239.6 [233.5–252.6] | no significant difference |

## Scenario `spa`

| target | success | warm fetch ms median [95% CI] | peak PSS MiB | cold start ms | vs baseline (latency) |
|---|---|---|---|---|---|
| chrome-cft | 100% | 146.6 [145.5–147.7] | 324.6 [318.9–330.4] | 344.2 [338.3–347.5] | 0.6× |
| chrome-headless-shell | 100% | 84.0 [83.4–84.4] | 85.2 [84.9–85.4] | 233.6 [232.4–241.4] | baseline |
| firefox-pw | 100% | 226.1 [222.3–230.9] | 508.8 [505.9–515.9] | 418.2 [415.0–422.1] | 0.4× |
| lightpanda | 100% | 62.9 [62.4–63.6] | 17.7 [17.5–18.8] | 231.9 [229.8–236.8] | 1.3× |
| playwright-chromium | 100% | 85.0 [84.6–85.8] | 172.0 [171.6–172.8] | 236.2 [234.0–252.1] | 1.0× |

## Scenario `static`

| target | success | warm fetch ms median [95% CI] | peak PSS MiB | cold start ms | vs baseline (latency) |
|---|---|---|---|---|---|
| chrome-cft | 100% | 101.0 [100.3–102.2] | 296.4 [286.1–303.6] | 341.7 [336.8–347.0] | 0.4× |
| chrome-headless-shell | 100% | 42.2 [41.4–42.5] | 87.1 [86.6–87.6] | 238.2 [235.9–241.4] | baseline |
| firefox-pw | 100% | 166.0 [164.2–169.2] | 505.4 [499.5–512.3] | 417.3 [414.9–423.1] | 0.3× |
| lightpanda | 100% | 19.0 [18.5–21.0] | 18.3 [17.6–18.4] | 229.4 [228.7–234.9] | 2.2× |
| playwright-chromium | 100% | 42.2 [41.8–42.9] | 171.9 [170.1–172.3] | 245.8 [239.0–254.2] | no significant difference |

---
Run on 13th Gen Intel(R) Core(TM) i5-13420H (12 cores), kernel 7.0.0-38-generic, load 0.54, git 5a77730, 2026-10-24T02:42:04.545466+00:00.
Method: each cell = independent lifecycles (fresh process); the sample unit is the per-lifecycle median of warm fetches; CIs are 95% bootstrap; a ratio is shown only when CIs do not overlap (n>=10 lifecycles). Latency compares only successful fetches; success rate is reported beside it.