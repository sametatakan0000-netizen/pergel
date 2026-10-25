# REA Hedef: AI-Native Tarayıcılar (2026-10 pazar tablosu)

> Kaynak: kamuya açık 2026 ürün sayfaları, yardım merkezleri ve güvenlik
> duyuruları (ek kaynak: teknik blog incelemeleri). REA kuralları geçerli: salt
> okunur analiz, lisans kırma/atlama yok. Ürünün (AI-Native Browser Engine
> SaaS) **fiili rakipleri** burada; Chromium çatalı 5'li REA bunların altyapısını
> gösteriyordu, bu doküman ürün katmanını ekliyor.

## 1. Üç kategori (Fastio/taxonomy)

| Kategori | Ürünler | Karakter |
|---|---|---|
| Chat-augmented | Edge, Opera, Brave, Chrome+Gemini | Geleneksel gezinme + yan panel asistan |
| AI-first | Comet, Dia, (Atlas ⚰) | Arayüz modelin etrafında kurulu |
| Agentic | Fellou, Genspark, Opera Neon, BrowserOS | Otonom görev yürütme öncelikli |

## 2. Ürün tablosu (2026-10)

| Ürün | Motor | Agent | Platform | Fiyat | Eklenti |
|---|---|---|---|---|---|
| **Perplexity Comet** | Chromium | ✓ (ücretsiz, kotalı) | Win/mac/iOS/Android | Ücretsiz; Pro $20, Max $200 | CWS uyumlu |
| **ChatGPT Atlas** ⚰ | Chromium | ✓ (güçlü, ücretli) | macOS | 09.08.2026'da kapatıldı → ChatGPT masaüstü + Chrome eklentisi | CWS (chatgpt.com'da kısıtlı) |
| **Google Chrome + Gemini** | Chromium | Auto Browse (ABD, AI Pro/Ultra) | Tümü | Panel ücretsiz; agent $19.99+ | CWS tam |
| **Microsoft Edge + Copilot** | Chromium | Browse with Copilot (ABD) | Tümü | Ücretsiz; agent M365 Premium | Edge Add-ons + CWS |
| **Brave Leo** | **Chromium 114 (42 major lag!)** | ✗ (test bayrağı) | Tümü | Ücretsiz; Premium $14.99 | CWS uyumlu |
| **Dia (Atlassian)** | Chromium | sınırlı | macOS (Apple Silicon) | Ücretsiz; Pro $20 | CWS (ikinci sınıf) |
| **Opera Neon** | Chromium (154) | ✓ (ücretli $19.90) | Win/mac | Browser + dış agent MCP/CLI ücretsiz (Ağu 2026+) | CWS + Opera Addons |
| **Genspark** | Chromium | ✓ | Win/mac | Ücretsiz; Plus $24.99 | — |
| **Fellou** | Chromium | ✓ (developer) | Win/mac | Ücretsiz deneme; Plus $20 | — |
| **BrowserOS** | Chromium (açık kaynak) | ✓ (yerel, BYOM/Ollama) | Win/mac | Ücretsiz | CWS tam + MCP/CLI |
| **Firefox Smart Window** | Gecko | ✗ | Win/mac (ABD/Kanada/Fransa) | Ücretsiz (beta) | AMO + **MV2 webRequest blocking korunur** |
| **Arc** ⚰ | Chromium | Arc Max | mac/Win | Ücretsiz | Bakım modu (May 2025'ten beri) |

## 3. Agent çalışma modelleri (güvenlik farklılaştırıcısı)

| Ürün | Çalışma yolu | Ayrı profil? | Hassas işlemde onay |
|---|---|---|---|
| Claude in Chrome | Chrome eklentisi | ✗ (senin Chrome'un) | Yapılandırılabilir; Cowork'ta classifier + auto-approve |
| Gemini Auto Browse | Chrome içi + bulut tarayıcı | ✓ (bulut seçeneği) | Google "sen sorumlusun" diyor |
| Comet | Tarayıcının kendisi | ✗ | Belirsiz (yardım sayfalarında yok) |
| ChatGPT | Masaüstü içi + bulut | ✓ (kendi durumu) | ✓ yapılandırılabilir (Always ask/auto/allow) |
| Opera Neon | Ayrı tarayıcı | ✓ | Bağlanan agent'a bağlı |
| Edge Browse with Copilot | Edge içi | ✗ | ✓ (satın alma/e-posta öncesi); şifre/cüzdan erişimi yok |

**Sentez çıktısı:** Prompt injection (gizli sayfa talimatı) 2026'da çözülmemiş
durumda — Comet/Ağustos 2025 Brave araştırması, LayerX Gmail sızıntısı. Comet
sınıflandırıcı + Trail of Bits denetimi + açık kaynak **BrowseSafe** (Ara 2025)
ile savunma kurdu. Bizim motorumuzda bunun **ayrı profil + onay kapısı + içerik
talimat filtresi** olarak doğrudan üretilmesi büyük avantaj.

## 4. Bizim konumumuz (güncel)

Kazanç alanları:
- **Brave'in 42 major patch-lag'i** ve **Vivaldi'nin kapalı CDP'si** bizim için
  hazır güvenlik/otomasyon argümanı.
- **Firefox Smart Window** gibi "açık MV2 blocking webRequest" yüzeyi, Google'ın
  CWS'den MV2'yi tamamen kaldırmasıyla (31.08.2026) **tek alternatif** oldu —
  gizlilik/engelleme ürünlerinin son sığınağı. Bizim için ya tam MV3 destek ya
  da Firefox-vari blocking yüzeyi sunmak karar noktası.
- **Opera Neon'un MCP/CLI'sı ücretsiz** (Ağu 2026+): "dışarıdan agent sürme"
  beklentisi standartlaştı. Bizim motorun da **MCP + CDP + CLI** üçlüsünü
  açıkça sunması gerekiyor.
- **Ayrı profil izolasyonu** (ChatGPT/Opera modeli) Comet'in zayıf noktası;
  bizde varsayılan olmalı.

Kaybedilecek alanlar:
- Hazır kullanıcı tabanı/marka (Comet ücretsiz + 4 platform).
- Model derinliği (Google/OpenAI/Anthropic'in kendi modelleri).
- Atlas örneği: pazar **9 ayda** bile değişiyor — Chrome-eklenti + masaüstü
  uygulamasına dağılan agent işlevleri. Bizim hız avantajımız olmalı.
