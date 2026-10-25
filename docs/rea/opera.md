# REA target — Opera (Linux x64)

**Level:** `dynamic-ok` (HFY blanket approval 2026-10-25). **Stage:** static done, dynamic pending.

## Acquire & fingerprint (verified 2026-10-25)
- **Source:** official apt repo `deb.opera.com/opera-stable` (`Packages` index — URL not guessed).
- **Package:** `opera-stable_138.0.6044.24_amd64.deb`, 143,482,144 bytes.
- **sha256:** `0ee45e6d17d2153860251e614ba09d6edca2fe2a32f40198a140896aaa3daf60` — **matches the repo `SHA256:` record exactly.**
- **Version:** `138.0.6044.24`. **Section:** `non-free/web` (note: non-free, unlike Brave/Edge/Vivaldi which are `web`).
- **Installed-Size:** 379,517 KiB (~371M). **Maintainer:** Opera Packaging Team. **Homepage:** opera.com/browser/.
- **Install layout:** `/usr/lib/x86_64-linux-gnu/opera-stable/` (not `/opt` like the others).

## Update mechanism (concrete)
- Bundled **`opera_autoupdate` binary, version 1.3.0** (`opera_autoupdate.version`) — Opera ships its own updater as a first-class executable (separate from apt), unlike the CRX component channel.
- Also `opera_crashreporter`, `opera_sandbox`, `chrome_crashpad_handler`.

## Bundled components (manifest.json)
- `opera-intro` extension v2.0.153 (no update_url) — a bundled first-run extension.
- No Widevine/MEIPreload manifest at inspected depth (on-demand fetch likely) — **not verified from static**.

## Embedded hosts (strings, host level)
`www.opera.com`, `addons.opera.com`, `cashback.opera.com`, `help.opera.com`, `sync.opera.com`, `auth.opera.com`, `speeddials.opera.com`, `flow.opera.com`, `weather.opera-ap…`, `opera.atlassian…`, **`go.mail.ru`** (Russian-market search deal — see cross-target note below).

## What we could NOT verify (static)
- Exact Chromium major base (branch-heads not pulled this pass).
- Widevine presence/behavior (on-demand).
- Actual auto-update traffic from `opera_autoupdate` (dynamic phase).

## Files
`/tmp/rea/downloads/opera-stable_138.0.6044.24_amd64.deb`, extracted `/tmp/rea/extracted/opera/`.
