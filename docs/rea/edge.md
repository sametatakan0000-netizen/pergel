# REA target — Microsoft Edge (Linux x64)

**Level:** `dynamic-ok` (HFY blanket approval 2026-10-25). **Stage:** static done, dynamic pending.

## Acquire & fingerprint (verified 2026-10-25)
- **Source:** official apt repo `packages.microsoft.com/repos/edge` (`Packages` index — URL not guessed).
- **Package:** `microsoft-edge-stable_156.0.4314.42-1_amd64.deb`, 191M.
- **sha256:** `a8642f829e105fe7a4ac440548e6fa7eb726b49fff8ffc6a27f3d0fb25a5b405` — **matches the repo `SHA256:` record exactly** (the first parse mis-paired SHA/lines; the corrected record block confirms the match).
- **Version (`msedge --version`):** `Microsoft Edge 156.0.4314.42`.
- **Chromium branch-heads (extracted):** `7727` (`b28eac7a1a97ec8d7bc58eca0242958254be494d`).
- **Installed-Size:** 688,008 KiB (~672M) — ~2× Brave, reflecting bundled Microsoft services.
- **Maintainer:** Microsoft Edge for Linux Team. **Section:** web.
- **Signature:** `.deb` channel is GPG-signed by the Microsoft repo; apt `SHA256:` matches.

## Bundled components (manifest.json)
- `WidevineCdm` 4.10.3050.1, MV2, update `https://clients2.google.com/service/update2/crx`.
- `MEIPreload` 1.0.7.1652906823, MV2, update `https://clients2.google.com/service/update2/crx`.

Widevine inspected as black box only (manifest/presence) — no DRM circumvention per hard lines. Note: Widevine version 4.10.3050.1 here is **older than Chrome for Testing's 4.10.3112.0** — component patch-lag signal.

## Embedded hosts (strings)
Host scan returned no matched `msedge`-specific external hosts in this pass (the `msedge` binary embeds service URLs under different tokens). The `msedge-management-service` and `msedge-sandbox` binaries are present (enterprise management surface). To enumerate Microsoft service endpoints properly, scan the full string set in the dynamic phase.

## What we could NOT verify (static)
- Exact Chromium major base (branch-heads `7727` is concrete; major mapping not confirmed from strings — legacy `Chrome/70.x`, `Chrome/99.x` tokens present).
- Microsoft telemetry/service endpoints (not matched this pass).
- Auto-update mechanism (Edge uses its own updater + apt repo).

## Files
`/tmp/rea/downloads/microsoft-edge-stable_156.0.4314.42-1_amd64.deb`, extracted tree `/tmp/rea/extracted/edge/`.
