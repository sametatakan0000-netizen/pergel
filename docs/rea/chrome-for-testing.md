# REA target — Chrome for Testing (Linux x64)

**Level:** `dynamic-ok` (HFY blanket approval 2026-10-25).
**Stage reached:** static inspection complete. Dynamic (mitmproxy/strace) not yet run.
Method per `docs/rea/README.md`.

## Acquire & fingerprint (verified 2026-10-25)

- **Source of truth:** `https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json`
  (official availability manifest — URLs read from here, not guessed).
- **Version:** `Google Chrome for Testing 156.0.8078.47` (`chrome --version`).
- **ChromeDriver:** `156.0.8078.47 (1d17a2e2ee147bb7d6ae2ab6abdb3a2510c17775-refs/branch-heads/8078@{#1313})`.
- **Packages downloaded** (sha256):
  - `chrome-linux64.zip` — `e6c94490f0b6b337225aeb2d2a5034858516b7017356980ba94f5176d8774a50` (190.9M)
  - `chromedriver-linux64.zip` — `2a5024610c53f340a1aaa5d9a3e2a4fa448be7d71cca5238bd8c3c7f16181df4` (11.3M)
- **Signature status:** the `.zip` channel ships **no GPG/`.sig` artifact** (only 3 `manifest.json` component descriptors found). Integrity here is the HTTPS channel + the availability-JSON digest; the `.deb` channel is the signed one. Recorded as-is — no signature claim made for the zip.

## Bundled components (from their `manifest.json`)

| Component | Version | Manifest | Update channel |
|---|---|---|---|
| WidevineCdm | 4.10.3112.0 | MV2 | `https://clients2.google.com/service/update2/crx` |
| MEIPreload (Media Engagement) | 1.0.7.1652906823 | MV2 | `https://clients2.google.com/service/update2/crx` |
| hyphen-data | 1.0.0.0 | MV2 | (none declared) |

Widevine is the DRM module — inspected only as a black box (manifest + presence);
its internals are **out of scope per hard lines** (no DRM circumvention).
Widevine declares codecs `vp8,vp09,avc1,av01`, encryption `cenc,cbcs`,
`persistent-license-support: false`, interface v10 / host v10,11.

## Dependencies (`deb.deps`, full list captured)

Standard desktop stack: `libnss3`, `libnspr4`, `libgtk-3-0|libgtk-4-1`,
`libgbm1`, `libvulkan1`, `libxkbcommon0`, `libasound2`, `ca-certificates`,
`fonts-liberation`, `wget`, `xdg-utils`, plus X11/xcb libs. No unusual or
proprietary system dependency beyond the Chromium norm.

## Update mechanism

- Component updaters (Widevine, MEI) call the **CRX update service**
  (`clients2.google.com/service/update2/crx`) — the same Web-Store CRX endpoint.
- Whether the CFT binary itself auto-updates (Omaha client) **not verified from
  static strings** — the category regex scan over 687,169 extracted strings found
  only truncated hosts (`update.googleap…`, `clients2.google.com/t`). CFT is
  expected to be a fixed/no-auto-update install, but that is an expectation, not a
  verified finding — check in the dynamic phase.

## Embedded endpoints observed (binary strings, host level)

Distinct Google hosts referenced include: `accounts.google.com`,
`chromewebstore.google.com`, `chrome.google.com/sync`, `chrome.google.com/webstore`,
`beacons*.gvt2.com` / `beacons*.gvt3.com` / `beacons.gcp.gvt2.com`,
`update.googleap…` (truncated), `access.workspace.google.com`, and the
`*.googleusercontent.com` / Workspace service surface (`c.docs.google.com`,
`calendar.google.com`, `classroom.googleap…`). Full list:
`/tmp/rea/logs/chrome-strings.txt` (687,169 lines).

Grouping update/crash/safebrowsing/metrics endpoints by category returned **0
distinct full URLs** because the embedded strings are truncated mid-URL by the
binary's string table. Category counts are therefore **not asserted** — only the
host names above are confirmed present.

## What we could NOT verify (static only)

- Actual network traffic at runtime (needs mitmproxy in a clean profile).
- Safe Browsing / UMA metrics endpoints specifically (truncated strings).
- Whether the `chrome_sandbox`/suid sandbox is active in our environment.
- Signature chain beyond the zip's absence of a `.sig`.

## Files

- Downloads + extracted tree + string dump: `/tmp/rea/` (`downloads/`, `extracted/`, `logs/`).
