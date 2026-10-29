# Pergel Launch Pack

## 1. Show HN Post (English)

**Title:** Show HN: Pergel – Privacy-first browser engine with AI, built for agents

**Body:**
Hey HN! We built Pergel — an open-source browser engine that's privacy-first and AI-native.

**What it does:**
- SSRF-guarded web extraction (browse, extract, crawl) via clean REST API
- Built-in AI mode: query fan-out, grounded citations, multi-model router
- Adblocking: EasyList + EasyPrivacy compiled to binary automata (ABP + uBlock syntax)
- Zero telemetry, zero data collection, BYOK (your keys stay local)
- Web UI control panel + MCP tool server (WebMCP-ready)
- 8 languages, RTL support, session record/replay

**What we DON'T do (on purpose):**
- No stealth/anti-detection for bypassing paywalls or bot walls
- No residential proxies or CAPTCHA solving
- No user tracking, ever

**Tech:** Python + CDP (Chrome DevTools Protocol), 300+ tests, MIT licensed.

**Links:**
- GitHub: https://github.com/sametatakan0000-netizen/pergel
- Docs: README + docs/ folder

Would love feedback on the architecture — especially the SSRF-guarded extraction pipeline and the Pareto-dominance model router.

---

## 2. Reddit r/opensource + r/privacy (English)

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
→ 8 languages, RTL, WebMCP-ready

3/5: The "defence, not evasion" principle:
→ We build SSRF/egress/privacy protection ✅
→ We DON'T build stealth to bypass paywalls ❌
→ We DON'T solve CAPTCHAs or use residential proxies ❌
→ Security = protecting YOU, not fooling others

4/5: Under the hood:
→ Python + Chrome DevTools Protocol
→ 300+ tests, TDD throughout
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
→ 300+ test, TDD
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

## 5. Launch Checklist

- [ ] Post to Show HN (best time: Tue-Thu 10am ET)
- [ ] Post to r/opensource (Tue/Wed)
- [ ] Post to r/privacy (weekday)
- [ ] Post to r/selfhosted (weekend)
- [ ] X/Twitter thread (same day as Show HN)
- [ ] Product Hunt (Thu or Tue)
- [ ] Dev.to crosspost
- [ ] LinkedIn post (EN + TR)
- [ ] Share in relevant Discord/Telegram groups
