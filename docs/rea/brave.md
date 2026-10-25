# REA target — Brave (Linux x64)

**Level:** `dynamic-ok` (HFY blanket approval 2026-10-25). **Stage:** static done, dynamic pending.

## Acquire & fingerprint (verified 2026-10-25)
- **Source:** official apt repo `brave-browser-apt-release.s3.brave.com` (`Packages` index — URL not guessed).
- **Package:** `brave-browser_1.52.126_amd64.deb`, 103M.
- **sha256:** `33fdb9605a844f81bcf52ee286216281ed38efe7e4fe358aa44883f0edb65bbe` — **matches the repo `SHA256:` record exactly.**
- **Version (`brave --version`):** `Brave Browser 114.1.52.126`.
- **Chromium base (CONFIRMED dynamic 2026-10-25):** `Chrome/114.0.5735.133`, **V8 11.4.183.23**, branch-heads `5735`. Three signals agree: CDP `Browser` field, `navigator.userAgent` (`Chrome/114.0.0.0`), V8 version.
- **Installed-Size:** 332,249 KiB (~324M). **Maintainer:** Brave Software. **Section:** web.
- **Signature:** `.deb` channel is signed by the Brave apt repo (GPG); not re-verified here beyond the apt `SHA256:` match.

## Bundled components (manifest.json)
- `MEIPreload` 1.0.7.1652906823, MV2, update channel `https://clients2.google.com/service/update2/crx`.
- No Widevine manifest found at the inspected depth (Brave fetches CDM on demand) — marked **not verified from static**.

## Embedded hosts (strings, host level)
`www.googleap…` (truncated, 41×), `support.google.com`, `www.google.com`, `beacons*.gvt2.com`/`beacons*.gvt3.com`/`beacons.gcp.gvt2.com` (21× each), `support.brave.com`, `www.bing.com`. Bing presence = Brave's default-search deals (a differentiator vs stock Chromium).

## Dynamic phase (2026-10-25)
- **Chromium base RESOLVED: 114.0.5735.133 / V8 11.4** (was the open question — now confirmed via headless CDP). Brave is the single biggest patch-lag outlier: **42 major versions behind** Chrome-for-Testing/Edge (156).

## What we could NOT verify
- Why Brave 1.52.126 (newest `stable` in its apt repo) is still on Chromium 114 — either the apt `stable` channel lags or Brave's 1.x numbering doesn't track recency. Flag for follow-up.
- Widevine presence/behavior (on-demand fetch).
- Actual traffic, auto-update path, telemetry endpoints (truncated strings).

## Files
`/tmp/rea/downloads/brave-browser_1.52.126_amd64.deb`, extracted tree `/tmp/rea/extracted/brave/`.
