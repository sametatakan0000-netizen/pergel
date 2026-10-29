# Platform Araştırma Raporu — Pergel Pazarlama (2026-10-29)

> Her platformun kuralları, algoritması, en iyi pratikleri ve riskleri.
> Kaynaklar: resmi kurallar, 2026 güncel rehberler, topluluk deneyimleri.

---

## 1. Hacker News (Show HN)

### Kurallar (resmi)
- **Show HN**: "Yaptığın bir şey, insanların deneyebileceği" olmalı. Blog post, signup page, newsletter DEĞİL
- **Non-trivial olmalı**: "Quickly-generated one-offs" post etme
- **Kişisel deneyim**: Kendi üzerinde çalıştığın ve tartışabileceğin bir şey
- **Signup/email bariyeri yok**: İnsanlar kolayca denemeli
- **Yeni özellik/upgrade**: "Foo 1.3.1 çıktı" genellikle yeterince substantial değil. Major overhaul olabilir
- **Arkadaşlardan upvote isteme**: Yasak
- **AI-generated metin**: Yasak — "Write your text yourself"
- **Otomatik posting**: Yasak
- **Site adı başlıkta**: Çıkar (link yanında zaten görünüyor)
- **Clickbait yok**: Büyük harf, ünlem, "amazing/müthiş" yok

### Algoritma (2026)
```
score = (upvotes - 1) / (age_in_hours + 2)^1.8
```
- **İlk 60-90 dakika kritik**: İlk saatteki oylar çok daha değerli
- **Erken velocity kazanır**: Yavaş 50 upvote, hızlı 20 upvote'a kaybeder
- **Zamanlama**: Salı-Perşembe, 8-10am ET
- **İlk yorum**: Kendi postuna ilk yorumu yaz (context ekler, tartışmayı başlatır)
- **2 saat boyunca her yoruma cevap ver**

### Tavsiye
- ✅ Pergel için **mükemmel uyum** — dev tool, open source, denenebilir
- ✅ "Show HN: Pergel – Privacy-first browser engine with AI extraction"
- ✅ Demo linki koy (kayıt gerektirmeyen)
- ❌ Lansman kopyası, basın bülteni, marketing dili
- ⚠️ Birçok iyi submission ölür — tahmin edilemez kanal

### HN'de başarılı benzer örnekler
- "Show HN: Open-source browser for AI agents" (47336171) — browser + AI = ilgi çekti
- "I worked on a new browser for 2 years" (49128826) — kişisel hikaye + teknik derinlik

---

## 2. Reddit

### ⚠️ KRİTİK: r/opensource AI PROJELERİNİ YASAKLADI (Ekim 2026)
- "Uses AI, is made by AI, or is AI-focused" projeler **tamamen yasak**
- Solo developer'lar da dışlanmış
- İngilizce olmayan kullanıcılar da yasak
- **Pergel buraya POST ATAMAZ** — AI-focused bir proje

### Güvenli Subreddit'ler

| Subreddit | Üye | Self-Promo Kuralı | Pergel Uyumu |
|---|---|---|---|
| **r/SideProject** | ~500K | Haftalık showcase thread | ✅ Mükemmel |
| **r/alphaandbetausers** | ~200K | Doğrudan paylaşım OK | ✅ İyi |
| **r/selfhosted** | 766K | Şartlı: production-ready + docs gerekli | ✅ İyi (self-hosting vurgusu) |
| **r/SaaS** | 386K | 60 günde 1 post | ⚠️ SaaS odaklı değil |
| **r/privacy** | ~1M | Değer odaklı paylaşım | ✅ Mükemmel (privacy-first) |
| **r/indiehackers** | ~100K | 1 post/ay | ✅ İyi |
| **r/IMadeThis** | ~100K | Showcase topluluğu | ✅ İyi |
| **r/webdev** | ~2M | Şartlı, yorumlarda paylaşım | ⚠️ Dikkatli ol |
| **r/programming** | ~6M | Teknik içerik OK, promo yok | ⚠️ Blog post olarak |
| **r/ArtificialIntelligence** | ~1M | Değer odaklı | ✅ İyi (AI extraction) |

### Reddit Genel Kuralları
- **9/10 kuralı**: 10 postun 9'u başkasının içeriği olmalı
- **Önce topluluğa katıl**: İlk post'tan önce yorum yap, katkı sağla
- **Değer odaklı**: "Satıyorum" değil, "bakın ne yaptım, ne düşünüyorsunuz?"
- **Haftalık thread'leri kullan**: Çoğu subreddit'te self-promo thread'i var
- **Asla upvote isteme**

### Tavsiye
- ✅ r/privacy → ana Reddit hedefi (privacy-first mesajı)
- ✅ r/selfhosted → self-hosting vurgusu ile
- ✅ r/SideProject → showcase
- ❌ r/opensource → YASAK (AI ban)
- ⚠️ r/programming → sadece teknik blog post, link değil

---

## 3. Product Hunt

### Kurallar
- **Ücretsiz** lansman
- **12:01 AM Pacific**'te başla (tüm günü alırsın)
- **1 ay önceden** planlanabilir
- **Upvote isteme**: Yasak. Geri bildirim iste
- **Gallery**: 1270×760px, en az 2 görsel
- **Hunter vs Maker**: Kendi ürününü kendin hunt edebilirsin
- **43 adımlık checklist** var (getlaunchlist.com)

### Strateji
1. **Pre-launch**: Hesap oluştur, geçmişi olsun, topluluğa katıl
2. **Lansman günü**: 12:01 AM PT'de paylaş, gün boyunca cevap ver
3. **Topluluğa önceden duyur**: Email listesi, sosyal medya
4. **Maker comment**: İlk yorumu kendin yaz (hikayeni anlat)
5. **Geri bildirim iste**: "What do you think?" de, "Upvote please!" DEĞİL

### Tavsiye
- ✅ Pergel için uygun (dev tool, open source)
- ⚠️ Hazırlık gerektirir (görseller, video, açıklama)
- ⚠️ Lansman günü tam gün bağlılık gerektirir
- 📅 Sıralamada Show HN'den SONRA olmalı

---

## 4. Skool

### Yapısı
- **Topluluk platformu**: Kurs + topluluk + gamification
- **Ücretsiz ve ücretli** topluluklar var
- **AI/dev tool toplulukları** aktif (Claude Code Club 8.9K üye, $9/ay)
- **Keşif**: skool.com/discover

### Strateji
1. **Mevcut topluluklara katıl** (AI, dev tool, indie hacker)
2. **Değer sağla**: Soruları cevapla, deneyim paylaş
3. **Kendi topluluğunu kur**: Ücretsiz, Pergel kullanıcıları için
4. **Cross-promotion**: Diğer topluluklarda bahset

### Tavsiye
- ✅ Niş AI/dev toplulukları hedeflenebilir
- ⚠️ Platform daha çok "para kazanma" odaklı — teknik proje tonu farklı olmalı
- ⚠️ Spam algısı yüksek — önce topluluğa katıl
- 📅 Lansman sonrası büyüme kanalı olarak kullan

---

## 5. X/Twitter

### Algoritma (2026)
- **En iyi saatler**: Pzt 2-3pm, Sal-Çar-Per peak saatleri
- **Viral formül**: 8-10am, 12-2pm, 5-7pm ET (ABD)
- **Mayıs 2026 algoritma güncellemesi**: Yeni kaynak kodu açıklandı
- **Thread'ler**: Tek post'tan daha fazla engagement
- **Görsel/video**: Metin-only'den daha fazla reach

### Strateji
1. **Thread** ile lansman (5 tweet, EN + TR)
2. **Görsel ekle** (screenshot, GIF, video)
3. **Hashtag**: #opensource #privacy #AI #buildinpublic
4. **Reply etkileşimi**: İlgili tweet'lere cevap ver
5. **Consistency**: Düzenli paylaşım

### Tavsije
- ✅ Ana sosyal medya kanalı
- ✅ xurl ile otomatikleştirilebilir (ücretsiz katman: 500 post/ay)
- ⚠️ Organik reach zor — hashtag ve timing önemli

---

## 6. Dev.to

### Strateji
- **Crosspost**: Blog yazılarını Dev.to'ya taşı
- **Teknik derinlik**: "How we built X" tarzı yazılar
- **Tag'ler**: #opensource #webdev #ai #python
- **Community**: Yorumlara cevap ver, diğer yazılara katıl

### Tavsiye
- ✅ Haftalık 1 teknik blog post
- ✅ "How Pergel blocks 113k ad rules in 0.34s" tarzı teknik yazı
- 📅 Lansman sonrası sürekli içerik kanalı

---

## 7. LinkedIn

### Strateji
- **TR + EN** ayrı post'lar
- **Profesyonel ton**: "Excited to share..."
- **Görsel**: Screenshot, mimari diagram
- **Hashtag**: #OpenSource #Privacy #AI #BrowserEngine

---

## 🎯 REVİZE LANSMAN SIRASI

Önceki sıralama r/opensource'i içeriyordu — YASAKLANDI. Yeni sıra:

```
Gün 0 (Salı-Perşembe, 8-10am ET):  Show HN ← ana lansman
Gün 0 (aynı gün):                   X/Twitter thread (HN linkiyle)
Gün 1:                              r/privacy + r/SideProject
Gün 2:                              r/selfhosted + r/IMadeThis
Gün 3:                              Dev.to teknik blog post
Gün 4:                              Product Hunt (12:01 AM PT)
Gün 5:                              Skool toplulukları
Gün 6:                              LinkedIn (EN + TR)
Gün 7+:                             Discord/Telegram grupları
```

---

## ⚠️ GENEL KURALLAR (tüm platformlar)

1. **Spam yapma** — sıkboğazlık olma, değer odaklı ol
2. **Platform-özel yaz** — kopyala-yapıştır yapma
3. **Upvote/like isteme** — her platformda yasak
4. **AI-generated metin kullanma** — HN'de özellikle yasak, diğerlerinde de algılanır
5. **Önce topluluğa katıl** — ilk post'tan önce yorum yap
6. **Gerçek veri kullan** — her claim benchmark ile destekli
7. **Hızlı cevap ver** — yorumlara 2 saat içinde
8. **Adaptif ol** — kurallar değişir, düzenli kontrol et

---

## Kaynaklar

- HN Show HN Guidelines: https://news.ycombinator.com/showhn.html
- HN Guidelines: https://news.ycombinator.com/newsguidelines.html
- HN Ranking Formula: https://www.flowjam.com/blog/how-to-get-on-the-front-page-of-hacker-news-in-2025-the-complete-up-to-date-playbook
- HN Marketing Guide: https://syften.com/blog/hacker-news-marketing/
- r/opensource AI Ban: https://www.tomshardware.com/tech-industry/artificial-intelligence/reddits-r-opensource-bans-ai-made-and-ai-focused-projects
- r/selfhosted Rules: https://leadsrover.io/subreddits/r/selfhosted
- Reddit Self-Promo: https://okara.ai/blog/subreddits-that-allow-self-promotion
- PH Checklist: https://getlaunchlist.com/checklists/producthunt
- X/Twitter Algorithm: https://www.socialpilot.co/blog/twitter-algorithm
- X/Twitter Best Times: https://sproutsocial.com/insights/best-times-to-post-on-twitter/
- Skool Communities: https://academygems.com/best/skool-communities-ai
