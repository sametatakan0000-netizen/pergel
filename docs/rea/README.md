# REA track — rules, legal basis, disclosure policy

**Status:** A5.1 created 2026-10-25. REA track green-lit by the user (2026-10-25);
this README is the standing rulebook for every `docs/rea/<target>.md` document
and every `scripts/rea/*` tool run. **Before any `dynamic-ok` work the user must
flip that target's row below** — that is the standing review gate.

## Goal

Understand each browser / AI-browser product's architecture, automation surface,
extension model, update mechanism, network behaviour and security posture so the
Vane extension can interoperate and can be positioned honestly (including
"Where we lose"). This is research on products we lawfully obtained and run on
our own machine — nothing more.

## What is allowed

- Analysing binaries/packages we lawfully obtained and run on our own machine
  (static inspection: unpacking, manifests, strings, bundled components).
- Passive observation of **our own** traffic and file/registry activity, in a
  clean test profile with our own account where a login is needed.
- Reading public docs, changelogs, source (open-source components), and public
  store listings. Leaked material, non-public data: **never** used.

**2026-10-25 — HFY granted all approvals** (machine access, sudo, every target `dynamic-ok`). The hard lines below are not waived by any approval.

## What is NOT allowed (hard lines)

- Breaking DRM / licence checks; bypassing paywalls or account entitlements.
- Defeating anti-bot or fraud-detection systems.
- Attacking, fuzzing, or load-testing vendor servers; anything beyond the
  traffic a normal session generates.
- Publishing vendor source code, proprietary blobs, or private keys.
- Testing against other users' data or accounts.
- Exploiting a vulnerability beyond the minimal proof on our own machine.

Findings that look like vulnerabilities are reported to the vendor
(**responsible disclosure, below**) **before** any publication.

## Responsible disclosure

1. Private report to the vendor's security contact (PSIRT / security@ /
   HackerOne — find the official channel; never a public issue first).
2. Include: affected version+hash, minimal reproduction on our own machine,
   impact assessment. No weaponised exploit, no mass scanning.
3. 90-day default disclosure window (extend once on reasonable vendor request).
4. Publication only after fix or window expiry, in neutral language, without
   exploit code or vendor source.
5. Everything is logged in `docs/rea/<target>.md` as "reported: date, channel,
   case id" — the log is the proof we did this right.

## Legal basis (recorded per the plan; NOT legal advice)

Interoperability / security-research exceptions differ by country:

- **US** — DMCA §1201(f) (reverse engineering for interoperability) and
  §1201(j) (security testing); the Copyright Office triennial §1201 exemptions
  for security research. CFAA still applies to anything beyond our own machine.
- **EU** — Software Directive 2009/24/EC Art. 6: decompilation for
  interoperability is permitted only to the extent necessary, only for
  interoperability, and only where the information is not readily available.
- **Türkiye** — FSEK (5846 sayılı) md. 38: interoperability-oriented
  decompilation of a lawfully obtained program is within the author's rights
  limits (bilgisayar programının çözümlenmesi/tersine mühendislik, sınırlı
  ölçüde). Exact scope varies with doctrine — get a local lawyer before
  anything beyond static inspection.

**Contract overrides nothing but still bites:** EULA/ToS clauses can prohibit
reverse engineering even where copyright law permits it. The legal exposure is
usually contractual (claims, account bans), rarely criminal — but it is real.
The **user decides the risk per vendor**. When in doubt: *observe, don't
decompile*.

## Per-vendor risk column

Levels: `observe-only` (what it does, no unpacking) < `static-ok` (unpack and
inspect locally) < `dynamic-ok` (run it under mitmproxy/strace in a clean test
profile). Every row is one-way conservative: upgrading a row requires the user's
explicit go and an update to this table **before** the work.

| Target | Level | Basis / notes |
|---|---|---|
| Our own extension & artifacts | unrestricted | ours; dog-food freely (A5.3 runs on `extension/manifest.json` first) |
| Lightpanda | n/a (open source) | read the source directly — no REA needed (A5.5) |
| Chrome for Testing  | dynamic-ok | explicitly published for automated testing/integration |
| Brave (Linux)  | dynamic-ok | A5.4 plan scope: static Linux inspection only |
| Edge (Linux)  | dynamic-ok | A5.4 plan scope: static Linux inspection only |
| Opera (Linux)  | dynamic-ok | A5.4 plan scope: static Linux inspection only |
| Vivaldi (Linux)  | dynamic-ok | A5.4 plan scope: static Linux inspection only |
| Perplexity Comet  | dynamic-ok | default for commercial AI browser (A5.6 needs Windows/Mac) |
| Dia  | dynamic-ok | default for commercial AI browser |
| Opera Neon  | dynamic-ok | default for commercial AI browser |
| Edge Copilot Mode  | dynamic-ok | default for commercial AI browser |
| Gemini in Chrome  | dynamic-ok | default for commercial AI browser |
| Claude in Chrome (extension)  | dynamic-ok | CRX from the Web Store is public — still observe-only until flipped |
| ChatGPT (Atlas) extension  | dynamic-ok | retired 2026-08-09; archive/analysis only |
| dynamic-ok (any) | — | granted 2026-10-25 by HFY for all rows above (blanket approval); hard lines below still apply |

## Method per target (summary — full template in the plan, §A5)

1. **Acquire & fingerprint** — version, hash, signature status, package format,
   update channel. Verify claims ourselves; never cite others' analyses as ours.
2. **Static inspection** — unpack (`7z`, `unzip`, `@electron/asar`, `omni.ja`,
   CRX header strip), manifests/permissions, bundled Chromium vs upstream
   (patch lag = finding), embedded endpoints (`strings`, URL extraction),
   telemetry SDKs.
3. **Dynamic observation** (needs `dynamic-ok`) — clean profile, own traffic via
   mitmproxy (CA only in that profile), `strace`/Procmon/`fs_usage`, CDP
   `Network`/`Fetch`, record the **page representation sent to the model** —
   that is what Vane's `browse_url` markdown competes with.
4. **Agent surface & safety review** (AI browsers) — prompt-injection
   separation, confirmation gates, allowlists, logged-in-session handling;
   output = threat table (vector, impact, mitigation observed).
5. **Deliverable** — `docs/rea/<target>.md` (text diagram, version+hash,
   endpoints, permissions, update mechanism, what we could **not** verify) and
   the cross-target `docs/rea/COMPARISON.md`.

Naming note: the plan calls the extension "Vane" pending an A9 name check.
