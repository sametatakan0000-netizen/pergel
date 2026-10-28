# Benchmark report

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

---
Run on 13th Gen Intel(R) Core(TM) i5-13420H (12 cores), kernel 7.0.0-38-generic, load 0.57, git a963c14, 2026-10-28T17:01:16.327261+00:00.
Method: each cell = independent lifecycles (fresh process); the sample unit is the per-lifecycle median of warm fetches; CIs are 95% bootstrap; a ratio is shown only when CIs do not overlap (n>=10 lifecycles). Latency compares only successful fetches; success rate is reported beside it.