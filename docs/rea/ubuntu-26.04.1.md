# REA target — Ubuntu 26.04.1 LTS Desktop (amd64 ISO)

**Level:** `dynamic-ok` (HFY blanket approval 2026-10-25). **Stage:** static done (ISO + SquashFS rootfs), dynamic (KVM boot) pending.

## Acquire & fingerprint (verified 2026-10-25)
- **Source:** `https://releases.ubuntu.com/26.04.1/` (official; URL not guessed).
- **ISO:** `ubuntu-26.04.1-desktop-amd64.iso`, 6,482,409,472 bytes (6.18 GiB).
- **sha256:** `601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f` — **matches the official `SHA256SUMS` record exactly.** `SHA256SUMS.gpg` (833 B) also fetched for signature chain (notarization not re-verified here).
- **`.disk/info`:** `Ubuntu 26.04.1 LTS "Resolute Raccoon" - Release amd64 (20260826)`, `cd_type: full_cd/single`.
- **Build date:** 2026-08-26.

## New installer architecture (`casper/install-sources.yaml`, `fsimage-layered`)
Ubuntu 26.04 ships a **layered install-source model** (not one monolithic rootfs):
- `ubuntu-desktop-minimal` (default): `minimal.squashfs` (3,436,847,104 B), preinstalled langs de/en/es/fr/it/pt/ru/zh.
- `ubuntu-desktop` (full): `minimal.standard.squashfs` (4,934,475,776 B) + `minimal.standard.live.squashfs` (793,112,576 B).
- **`enhanced-secureboot` variation**: separate `minimal.enhanced-secureboot.squashfs` with `snapd_system_label: enhanced-secureboot-desktop`.
- Per-language overlay squashfs (`minimal.{de,en,es,fr,it,pt,ru,zh}.squashfs`, ~16 MB each).
- **Kernel:** `linux-generic-hwe-24.04`.

This layered/variant structure (minimal vs full vs enhanced-secureboot, per-lang overlays) is directly relevant to the product's install-source parsing and to our own ISO fingerprinting.

## SquashFS rootfs (`casper/minimal.squashfs`)
- **Format:** SQUASHFS 4.0, **xz** compression, block size 131072, 7889 fragments. Extracted cleanly (3,432,136,704 B).
- **OS:** `Ubuntu 26.04.1 LTS (Resolute Raccoon)`, codename `resolute`, `ID_LIKE=debian`.

## Preinstalled browsers & GUI (from rootfs inventory)
- **Firefox 154.0-1** — shipped as a **snap** (`firefox_8763.snap`, `confinement: strict`, `base: core24`, channel `stable/ubuntu-26.04`). The dpkg entry is only the snap meta-pkg `firefox 1:1snap1-0ubuntu8`.
- **No deb Chromium/Chrome** preinstalled; `/snap/bin/firefox`, `firefox.geckodriver`, `geckodriver` present (automation surface via geckodriver — relevant to our bench's CDP/WebDriver discovery).
- `gnome-shell 50.1-0ubuntu1.2`, `snapd 2.76.3+ubuntu26.04`, `xdg-desktop-portal 1.21.1+ds-1ubuntu3`.

## Preinstalled snaps (seed, 13 total)
`bare_5`, `core24_1643`, `desktop-security-center_151`, `firefox_8763`, `firmware-updater_226`, `gnome-46-2404_164`, `gtk-common-themes_1535`, `hwctl_123`, `mesa-2404_1839`, `prompting-client_222`, `snap-store_1390`, `snapd-desktop-integration_391`, `snapd_27710`.

## APT sources (`etc/apt/sources.list.d/ubuntu.sources`)
`http://archive.ubuntu.com/ubuntu/` + `http://security.ubuntu.com/ubuntu/`, suites `resolute resolute-updates resolute-backports resolute-security`, components `main universe restricted multiverse`. Official mirrors only — no third-party repos baked in.

## Cross-target note
Firefox 154 (snap) sits between our Chromium-fork spread (Vivaldi 152 → CFT/Edge 156), so a browser-compatibility test matrix must span both Gecko 154 and the Chromium 152–156 range (and be aware Brave is far behind at 114).

## What we could NOT verify (static)
- Live boot behavior (KVM), installer interactive flow, and actual network/update endpoints at runtime — dynamic phase next.
- Snap auto-refresh behavior and connection to the snap store at runtime.

## Files
ISO + squashfs work moved to **real disk** `~/pergel (`downloads/`, `squash/`) — `/tmp` tmpfs (16 G) filled up during the 3.4 GB squashfs extract (errno 122 disk quota), so large artifacts live on `/dev/nvme0n1p2`.
