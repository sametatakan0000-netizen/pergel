# REA target — Brave (Linux x64)

**Level:** `dynamic-ok` (HFY blanket approval 2026-10-25). **Stage:** static done, dynamic pending.

## Acquire & fingerprint (verified 2026-10-25)
- **Source:** official apt repo `brave-browser-apt-release.s3.brave.com` (`Packages` index — URL not guessed).
- **Package:** `brave-browser_1.52.126_amd64.deb`, 103M.
- **sha256:** `33fdb9605a844f81bcf52ee286216281ed38efe7e4fe358aa44883f0edb65bbe` — **matches the repo `SHA256:` record exactly.**
- **Version (`brave --version`):** `Brave Browser 114.1.52.126`.
- **Chromium branch-heads (extracted):** `5735` (`fbfa2ce68d01b2201d8c667c2e73f648a61c4f4a`).
- **Installed-Size:** 332,249 KiB (~324M). **Maintainer:** Brave Software. **Section:** web.
- **Signature:** `.deb` channel is signed by the Brave apt repo (GPG); not re-verified here beyond the apt `SHA256:` match.

## Bundled components (manifest.json)
- `MEIPreload` 1.0.7.1652906823, MV2, update channel `https://clients2.google.com/service/update2/crx`.
- No Widevine manifest found at the inspected depth (Brave fetches CDM on demand) — marked **not verified from static**.

## Embedded hosts (strings, host level)
`www.googleap…` (truncated, 41×), `support.google.com`, `www.google.com`, `beacons*.gvt2.com`/`beacons*.gvt3.com`/`beacons.gcp.gvt2.com` (21× each), `support.brave.com`, `www.bing.com`. Bing presence = Brave's default-search deals (a differentiator vs stock Chromium).

## What we could NOT verify (static)
- Exact Chromium major base — the `--version` prefix `114.` and branch-heads `5735` disagree with a naive read; embedded `Chrome/` strings are legacy compat tokens (70.x/99.x), not the real base. Resolve via dynamic `navigator.userAgent` / `brave://version`.
- Widevine presence/behavior (on-demand fetch).
- Actual traffic, auto-update path, telemetry endpoints (truncated strings).

## Files
`/tmp/rea/downloads/brave-browser_1.52.126_amd64.deb`, extracted tree `/tmp/rea/extracted/brave/`.
