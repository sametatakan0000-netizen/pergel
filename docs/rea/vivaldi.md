# REA target — Vivaldi (Linux x64)

**Level:** `dynamic-ok` (HFY blanket approval 2026-10-25). **Stage:** static done, dynamic pending.

## Acquire & fingerprint (verified 2026-10-25)
- **Source:** official apt repo `repo.vivaldi.com/archive/deb` (`Packages` index — URL not guessed).
- **Package:** `vivaldi-stable_8.2.4133.94-1_amd64.deb`, 138,320,856 bytes.
- **sha256:** `2f63718129e20a231e3c4e503a9235e7ad2107a0285ddf5e5aadf6cbf7c638dd` — **matches the repo `SHA256:` record exactly.**
- **Version:** `8.2.4133.94-1`. **Section:** web. **Installed-Size:** 465,627 KiB (~455M). **Maintainer:** Vivaldi Package Composer. **Homepage:** vivaldi.com.
- **Install layout:** `/opt/vivaldi/` (`vivaldi` wrapper + `vivaldi-bin` real binary).

## Update mechanism
- `update-ffmpeg` binary + `downloads.vivaldi.com` / `update.vivaldi.com` hosts — Vivaldi ships a proprietary-codec updater (FFmpeg with proprietary codecs) alongside apt.
- No `opera_autoupdate`-style full updater seen; relies on `update.vivaldi.com` + apt repo.

## Bundled components (manifest.json)
- `PrivacySandboxAttestations` 2025.7.18.0 (no update_url) — Chromium Privacy Sandbox attestation bundle.
- `MEIPreload` 1.0.7.1652906823, MV2, update `https://clients2.google.com/service/update2/crx`.
- No Widevine manifest at inspected depth — **not verified from static**.

## Embedded hosts (strings, host level)
`return-404.vivaldi.com` (14×), `downloads.vivaldi.com` (12×), `help.vivaldi.com`, `update.vivaldi.com`, `crash.vivaldi.com`, `vivaldistatus.com`, `mail.google.com`, **`go.mail.ru`** + **`suggests.go.mail.ru`** (Russian-market search deal — see cross-target note).

## What we could NOT verify (static)
- Exact Chromium major base (branch-heads not pulled this pass).
- Widevine presence/behavior (on-demand).
- Behavior of `update-ffmpeg` (what it downloads; dynamic phase).
- Note: our bench probe earlier reported "vivaldi BLOCKED: no CDP DevTools port on launch" — automation surface differs from stock Chromium; verify DevTools flags dynamically.

## Files
`/tmp/rea/downloads/vivaldi-stable_8.2.4133.94-1_amd64.deb`, extracted `/tmp/rea/extracted/vivaldi/`.
