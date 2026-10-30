# Pergel Launch Pack

## 1. Show HN Post (English)

**Title:** Show HN: Pergel – Privacy-first browser engine with AI, built for agents

**Body:**
Hey HN! We built Pergel — an open-source browser engine that's privacy-first and AI-native.

**What it does:**
- SSRF-guarded web extraction (browse, extract, crawl) via clean REST API
- Built-in AI mode: query fan-out, grounded citations, multi-model router
- Adblocking: EasyList + EasyPrivacy compiled to binary automata (ABP + uBlock syntax)
- Tracker blocking: 60+ tracker domains blocked natively (EasyPrivacy-aligned)
- Crash recovery: sessions auto-persist, never lose tabs
- Memory saver: inactive tabs hibernate automatically
- Zero telemetry, zero data collection, BYOK (your keys stay local)
- Web UI control panel + MCP tool server (WebMCP-ready)
- 8 languages, RTL support, session record/replay

**What we DON'T do (on purpose):**
- No stealth/anti-detection for bypassing paywalls or bot walls
- No residential proxies or CAPTCHA solving
- No user tracking, ever

**Tech:** Python + CDP (Chrome DevTools Protocol), 802 tests, MIT licensed.

**Links:**
- GitHub: https://github.com/sametatakan0000-netizen/pergel
- Docs: README + docs/ folder

Would love feedback on the architecture — especially the SSRF-guarded extraction pipeline and the Pareto-dominance model router.

---

## 2. Reddit r/privacy + r/SideProject (English)

> ⚠️ r/opensource Ekim 2026'da AI projelerini yasakladı — POST ATMA

**Title:** I built Pergel: an open-source, privacy-first browser engine with AI extraction (no telemetry, BYOK)

**Body:**
After getting frustrated with browser automation tools that phone home, leak data, or require paid APIs, I built Pergel.

Key design decisions:
- **Defence, not evasion**: SSRF protection, egress control, rate limiting — but deliberately NO stealth/anti-detection for bypassing paywalls
- **BYOK**: Your AI keys stay on your machine. We never see them.
- **Zero telemetry**: No analytics, no crash reports, no usage tracking
- **Deterministic extraction**: CSS selectors, JSON-LD, regex — not LLM guesswork
- **Session record/replay**: Record HTTP traffic, replay it offline

Everything is MIT licensed. The repo has benchmarks, architecture docs, and honest gaps listed.

Would love your thoughts — especially on the "defence not evasion" boundary.

---

## 3. X/Twitter Thread (EN + TR)

**EN:**
🧵 1/5: Introducing Pergel — an open-source, privacy-first browser engine built for AI agents.

No telemetry. No data collection. BYOK. MIT licensed.

🔗 https://github.com/sametatakan0000-netizen/pergel

2/5: What makes it different?
→ SSRF-guarded web extraction (browse/extract/crawl)
→ AI mode with grounded citations + multi-model router
→ Adblocking compiled to binary automata (not string matching)
→ 60+ tracker domains blocked natively
→ Crash recovery + tab hibernation (memory saver)
→ 8 languages, RTL, WebMCP-ready

3/5: The "defence, not evasion" principle:
→ We build SSRF/egress/privacy protection ✅
→ We DON'T build stealth to bypass paywalls ❌
→ We DON'T solve CAPTCHAs or use residential proxies ❌
→ Security = protecting YOU, not fooling others

4/5: Under the hood:
→ Python + Chrome DevTools Protocol
→ 802 tests, TDD throughout
→ Session record/replay for deterministic testing
→ Structured error envelopes with request_id correlation

5/5: Star it, fork it, break it, tell us what's missing.

Everything's at github.com/sametatakan0000-netizen/pergel

⭐ Star if you believe privacy and AI can coexist.

---

**TR:**
🧵 1/5: Pergel — AI ajanları için tasarlanmış, gizlilik odaklı açık kaynak tarayıcı motoru.

Telemetri yok. Veri toplama yok. BYOK. MIT lisanslı.

🔗 https://github.com/sametatakan0000-netizen/pergel

2/5: Neden farklı?
→ SSRF korumalı web çıkarma (tarama/çıkarma/crawl)
→ Alıntılı AI modu + çoklu model yönlendirici
→ İkili otomata'ya derlenmiş reklam engelleme
→ 8 dil, RTL, WebMCP-hazır

3/5: "Savunma, hile değil" ilkesi:
→ SSRF/egres/gizlilik koruması ✅
→ Ödeme duvarı aşmak için gizlilik hilesi ❌
→ CAPTCHA çözme, konut proxy'si ❌

4/5: İç yapı:
→ Python + Chrome DevTools Protocol
→ 802 test, TDD
→ Deterministik oturum kayıt/tekrar

5/5: Star atın, fork'layın, kırın, eksikleri söyleyin.

⭐ Gizlilik ve AI'ın bir arada olabileceğine inanıyorsanız star atın.

---

## 4. Product Hunt (EN)

**Tagline:** Privacy-first browser engine with AI extraction. No telemetry. BYOK.

**Description:**
Pergel is an open-source browser engine that puts privacy first and AI second (never the other way around).

✓ SSRF-guarded web extraction API
✓ AI with grounded citations (no hallucinated sources)
✓ Adblocking compiled to binary automata
✓ Zero telemetry, zero data collection
✓ Bring Your Own Key — your AI keys stay local
✓ 8 languages, session record/replay, WebMCP-ready

Built for developers and AI agents who need reliable web access without sacrificing privacy.

---

## 4b. Skool Community (EN + TR)

**Title:** Pergel — Open-source privacy-first browser engine for AI agents

**Body (EN):**
Hey everyone! I built Pergel — a browser engine that AI agents use to read the web cheaply and privacy-respectingly.

Why it matters for this community:
→ If you build AI agents, you know the pain of token costs on messy DOM
→ Pergel's engine ladder keeps cheap pages cheap (verified benchmarks in repo)
→ Built-in ad blocking (113k+ rules) + tracker blocking (60+ domains), zero telemetry, BYOK
→ Crash recovery + tab hibernation (memory saver)
→ MIT licensed, 802 tests, fully open source

Not selling anything — just sharing what I built. Feedback welcome!

🔗 https://github.com/sametatakan0000-netizen/pergel

**Body (TR):**
Merhaba! Pergel'i yaptım — AI ajanlarının webi ucuza ve gizliliğe saygılı şekilde okuması için bir tarayıcı motoru.

Bu topluluk için neden önemli:
→ AI ajanı geliştiriyorsanız, dağınık DOM üzerinde token maliyetini bilirsiniz
→ Pergel'in motor merdiveni ucuz sayfayı ucuz tutar (repoda doğrulanmış benchmark'lar)
→ 113k+ kurallı yerleşik reklam engelleme + 60+ tracker engelleme, sıfır telemetri, BYOK
→ Crash recovery + tab hibernation (bellek tasarrufu)
→ MIT lisanslı, 802 test, tamamen açık kaynak

Satış yok — sadece yaptığım şeyi paylaşıyorum. Geri bildirimlerinize açığım!

🔗 https://github.com/sametatakan0000-netizen/pergel

---

## 5. Launch Checklist

- [ ] Show HN (Tue-Thu, 8-10am ET) ← ana lansman
- [ ] X/Twitter thread (same day as Show HN)
- [ ] r/privacy (weekday) — privacy-first mesaj
- [ ] r/SideProject (weekly showcase thread)
- [ ] r/selfhosted (self-hosting vurgusu ile)
- [ ] r/IMadeThis (showcase)
- [ ] Dev.to teknik blog post (How-we-built tarzı)
- [ ] Product Hunt (12:01 AM PT, tam gün bağlılık)
- [ ] Skool topluluklarına katkı + paylaşım
- [ ] LinkedIn (EN + TR)
- [ ] Discord/Telegram grupları

⚠️ r/opensource AI projelerini yasakladı (Ekim 2026) — POST ATMA!
📋 Detaylı platform araştırması: docs/marketing/platform-research-2026-10-29.md
