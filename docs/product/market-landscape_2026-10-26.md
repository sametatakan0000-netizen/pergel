# Pazar Haritası: AI Web-Surfing Yaklaşımları ve Konumlandırma
Tarih: 2026-10-26 · Kapsam: AI ajanlarının webi nasıl okuduğu/gezdiği yöntemler

> Not: Rakip fiyat ve özellikleri satıcı sayfaları ve üçüncü taraf incelemelerinden alındı (Eylül–Ekim 2026 itibarıyla). Satıcı kendi performans iddiaları (ör. "%67 daha az token", "%93 context tasarrufu") **kendi beyanıdır**, bağımsız doğrulanmadı. Bizim tarafta ölçülmemiş her şey `[ÖLÇÜLMEDİ]` olarak işaretli.

## 1. Üç kategori (AI ajanlarının web'e erişim yöntemleri)

| Kategori | Ne yapar | Örnekler |
|---|---|---|
| **A. Okuma / Markdown API** | URL → temiz Markdown/JSON. Gezinme yok, tek sayfa veya basit crawl. | Jina Reader, Firecrawl `/scrape`, Crawl4AI, Spider |
| **B. Arama + içerik** | Sorgu → sonuçların tam içeriği | Exa, Firecrawl `/search`, Jina `s.jina.ai`, Tavily |
| **C. Uzak tarayıcı / tarayıcı ajanı** | Tam tarayıcı oturumu; tıklama, form, JS, oturum | Browserbase, Browser Use (cloud), Cloudflare Browser Run, Steel, Firecrawl `/interact`, Playwright MCP, Vercel agent-browser |
| **D. Ajan-yerel yapısal yüzey** | Sitenin kendisi araçlarını ilan eder (WebMCP) | Chrome WebMCP (Chromium 146+), Cloudflare WebMCP desteği |

Pazarın ana eğilimi: A ve C kategorileri MCP sunucusu olarak paketleniyor; ajanlar "tarayıcı" yerine "araç" görüyor. Token maliyeti (ham DOM yerine kısa referanslar/Markdown) en çok pazarlanan tema.

## 2. Rakip konumlandırması

| Ürün | Kategori | Güçlü yan (satıcı + inceleme) | Zayıf yan / boşluk | Fiyat başlangıcı |
|---|---|---|---|---|
| Firecrawl | A + B + C(interact) | 7 endpoint (scrape/crawl/map/search/agent/interact/parse), LLM-hazır MD, JSON şema çıkarımı, change tracking, MCP, keyless deneme | Ajan modu kredi bazlı ve değişken; ekosistem büyük ama ağır | $16/ay (yıllık) |
| Jina Reader | A + B | `r.jina.ai/` ile sıfır kurulum, ücretsiz katman | Anti-bot yok, şema çıkarımı zayıf, JS render sınırlı | Ücretsiz / token bazlı |
| Exa | B | Hızlı semantik arama + içerik | Tarayıcı etkileşimi yok | (doğrulanmadı) |
| Browserbase / Browser Use Cloud | C | Stealth, CAPTCHA, residential proxy, ajan API | Her oturum ücretli; ajan başına maliyet | ~$0.02/tarayıcı-saat (Browser Use) |
| Cloudflare Browser Run | C | Global ağ, CDP erişimi, WebMCP, session kayıt/replay, Live View | Cloudflare ekosistemine bağlılık | (ölçülmedi) |
| Steel | C | Tek tuş sayfa içeriği/screenshot/PDF | Otomasyon ağırlıklı | (doğrulanmadı) |
| Vercel agent-browser | C (CLI) | Rust CLI, <50 ms boot, `@e1` referansları, ~%93 context tasarrufu (satıcı beyanı, Playwright MCP'ye karşı) | Yerel CLI; hosted değil | Açık kaynak |
| Playwright MCP | C | Standart, geniş ekosistem | Tam DOM/erişilebilirlik ağacı → yüksek token | Açık kaynak |
| Browser Use (OSS) | C | Açık kaynak Python/TS ajan, CLI | Kendi LLM anahtarı ve tarayıcı yönetimi gerekir | Açık kaynak |

## 3. Bizim konumumuz (kanıtlanmış / kanıtlanmamış)

**Mevcut yüzeylerimiz (koddan doğrulandı):**
- `POST /v1/jobs/browse` — asenkron tarayıcı işi (kendi motorumuz, Lightpanda/Chrome/Firefox/WebKit hedefleri)
- `POST /v1/search/fanout` — çoklu sorgu fan-out
- `POST /v1/chat/completions`, `/v1/models`, `/v1/router/complete`, `/v1/router/moa` — Oracle router (model yönlendirme)
- MCP: `browse_url`, `search_fanout`, `router_health` (+ tek sayfa araçları)
- Dahili: `html_to_clean_markdown` (Markdown dönüşümü) — **dışa açık bir Markdown/şema endpoint'i olarak doğrulanmadı**

**Ölçülmüş avantaj (benchmark, `competitive-benchmark_2026-10-26.md`):**
- Lightpanda: statik ~20 ms / ~17 MiB PSS; Chrome-CFT ~102 ms / ~528 MiB. Yani motor-seviyesinde hız ve bellek avantajı var.
- Bu avantaj **A kategorisi (okuma API)** için anlamlı: ağır tarayıcı açmadan sayfa okuma maliyeti düşük.

**Dürüst boşluklar (rakiplerde var, bizde yok veya doğrulanmadı):**
1. Crawl / site haritası (`/crawl`, `/map`) — `[YOK]`
2. Şema tabanlı JSON çıkarımı (`/extract`) — `[YOK / doğrulanmadı]`
3. Arama + tam içerik ürünü (`/search` benzeri, sayfa içeriğiyle) — kısmen (`search/fanout`), içerik dönüşümü `[doğrulanmadı]`
4. Anti-bot / CAPTCHA / residential proxy — `[YOK]` (kendi SSRF/egress güvenliğimiz var ama stealth yok; ve stealth'i pazarlamıyoruz — sert çizgi: aşma yok)
5. Session kayıt/replay ve Live View — `[YOK]`
6. Form/etkileşim adımları (`/interact` benzeri) — `[YOK / doğrulanmadı]`
7. WebMCP desteği — `[YOK]` (Chromium 146+ gerektirir; motorumuzun desteği ölçülmedi)
8. Token-verimli çıktı (ham DOM yerine kısa referans) — `[ÖLÇÜLMEDİ]` (agent-browser'a karşı karşılaştırma yapılmadı)

**Konumlandırma önerisi (ölçüme dayalı, abartısız):**
- Hedef pazar: "düşük maliyetli, kendi sunucunda çalışan, hafif motorla sayfa okuma + tarayıcı ajanı" (self-host + düşük bellek).
- Güçlü cümle (ölçüldü): "Statik sayfa okumada ~5× hızlı, ~30× düşük bellek (Chrome-CFT'ye karşı, 2026-10-26, git `a9b205f`)."
- Kaçınılacak: "Firecrawl'dan iyi" / "tüm web'i tarar" gibi ölçülmemiş genellemeler.

## 4. Eksik karşılaştırmalar (sonraki iş) — API anahtarı gerekmeden
Kendi kurulumumuzda bu hizmetler zaten hazır ve **Nous Portal Tool Gateway** üzerinden geliyor (`.env`'de harici anahtar yok):
- `~/.hermes/config.yaml` → `web.backend: firecrawl`, `browser.backend: browser-use`
- `hermes tools list` → `web` (Web Search & Scraping) ✓, `browser` (Browser Automation) ✓

Yani Firecrawl/Exa sınıfı erişim, Nous Portal aboneliği kapsamında; ayrı API anahtarı satın alınmayacak. Karşılaştırmalar bu altyapıyla:
- Aynı 50 URL setinde `web_extract` (Firecrawl destekli) vs bizim `browse_url` → süre, Markdown kalitesi, token sayısı.
- agent-browser vs bizim çıktı formatı → token sayımı (aynı sayfa seti).
- Bu iki ölçüm yapılmadan "daha az token" veya "daha iyi içerik" iddiası kullanılmaz.

## 4b. Ölçülen tüm tarayıcılar (tam liste, `competitive-benchmark_2026-10-26.md`)
Hedef, tek bir tarayıcı değil **tarayıcı motorları** üzerinden ölçüldü — AI ajanları da tam bu motorları sürüyor. Hepsi ölçülür:

| Hedef | Motor | Statik (ms) | SPA (ms) | Heavy (ms) | Bellek PSS (MiB) | Cold start (ms) |
|---|---|---|---|---|---|---|
| **lightpanda (bizim motor)** | Lightpanda | **20.4** | **63.7** | **23.9** | **~16–17** | **~246** |
| chrome-headless-shell | Chromium | 45.1 | 85.8 | 49.3 | ~202–206 | ~242 |
| playwright-chromium | Chromium | 42.6 | 85.0 | 50.1 | ~172–175 | ~250 |
| brave | Chromium | 96.2 | 139.0 | 107.9 | ~401–413 | ~342 |
| edge | Chromium | 94.2 | 134.0 | 106.5 | ~512–530 | ~402 |
| chrome-cft | Chromium | 104.4 | 146.9 | 121.8 | ~514–558 | ~354 |
| firefox-pw | Gecko | 165.7 | 225.9 | 181.7 | ~504–522 | ~419 |
| webkit-pw | WebKit | 191.9 | 227.5 | 212.2 | ~201–212 | ~245 |
| vivaldi | Chromium | **koşu kilitlendi** (zombie, exit 124) | — | — | — | — |

Kaynak: `~/.hermes/bench_runs/20261026_1851_main/raw.jsonl` + `REPORT.md`. Hepsi %100 başarı oranı; 3 ısıtmalı + 10 döngü. Vivaldi kararlılık bulgusu dürüstçe işaretli (iki bağımsız koşuda da zombie → harness kilitlenmesi). En yakın rakip chrome-headless-shell / playwright-chromium (~2× hızlılık farkı, ~12× bellek); masaüstü tarayıcılara (Brave/Edge/Chrome/Firefox/WebKit) karşı fark ~5–10× hız, ~25–35× bellek.

## 4c. Piyasadaki TÜM tarayıcılar (tam envanter)

### C1. Motor/çekirdek seviyesi (benchmark'ta ölçülen — hız & bellek)
Lightpanda (bizim), Chromium (Chrome-CFT, chrome-headless-shell, Brave, Edge, Vivaldi, Playwright-Chromium), Gecko (Firefox), WebKit (Safari/Playwright-WebKit). → Tablo 4b'de ölçüm sonuçlarıyla.

### C2. Bulut tarayıcı altyapıları (ajanların uzak tarayıcı sürdüğü servisler)
| Sağlayıcı | Stealth/geçme* | Oturum açma (median) | Fiyat/saat | Self-host | Not |
|---|---|---|---|---|---|
| Browser Use Cloud | **%90.5** | 493 ms | **$0.02** | Hayır (ajan OSS) | En yüksek geçme + en ucuz; profile sync |
| Anchor Browser | %82 | 2.800 ms | $0.05 (+$0.01/oturum) | Enterprise BYO-cloud | MFA/SSO/VPN uzmanı; tam stealth $2.000/ay kademede |
| Kernel | %80.5 | **318 ms** | $0.06–0.48 | Görsel açık kaynak | En hızlı oturum açma; per-saniye fatura |
| Browserbase | %78.5 | 877 ms | $0.10–0.12 | Hayır (private cloud) | Stagehand SDK; session replay; 50M oturum/2025 |
| Browserless | %77.5 | (401 hatası → ölçüm yok) | $0.18–0.24 | **Docker/K8s (OSS)** | BrowserQL (GraphQL) stealth; Firefox+WebKit |
| Steel | %74.5 | 3.509 ms | $0.08–0.10 | **Apache-2.0 OSS** | BYOP her planda; ajan leaderboard'ı var |
| Hyperbrowser | %73.5 | 1.417 ms | $0.10 | Hayır | Scrape+crawl API + sandbox |
| Bright Data Browser API | (Stealth Bench'te yok) | — | GB bazlı | Hayır | 400M+ residential IP; AIMultiple'da #1 iddiası |
| Zyte API | (yok) | — | GB/sayfa | Hayır | Yüksek hacim, tipli çıkarım |
| Scrapfly | (yok) | — | kredi | Hayır | HTTP + tarayıcı; Selenium uyumu; MCP Cloud |
| Cloudflare Browser Run | (yok) | — | (ölçülmedi) | Hayır (global ağ) | CDP, WebMCP, session kayıt, Live View |

\* Stealth = Stealth Bench V2, 100 bot-korumalı site × 2, tarafsız hakem (browser-use.com/benchmarks/browsers). Not: site seti bilerek zor seçilmiş, dengeli web örneklemi değil. Satıcı bağımsız benchmarkları farklı çıkıyor (Bright Data kendini #1 diyor) — bu alanda tarafsız veri yok, dikkat.

### C3. AI tarayıcıları / ajan-tarayıcılar (kullanıcı tarafı ürünler)
| Ürün | Mimari | Ücretsiz | Ajan modu | Not |
|---|---|---|---|---|
| Perplexity Comet | Bağımsız (masaüstü+Android+iOS) | **Evet** | Tam | Cross-platform tam; Amazon davası 2026'da aleyhine/lehine döndü |
| Claude in Chrome | Chrome eklentisi | Hayır | Tam | 10M+ kurulum (Haz 2026); GA Ağu 2026 |
| Gemini in Chrome (auto browse) | Chrome gömülü | Kısmen | Tam | Ücretli/ABD-özel başlangıç; Android'e genişledi |
| Opera Neon | Bağımsız | Ajan hedefi ücretsiz | Tam | 4 ajan (Do/Make/ODRA/Chat); MCP sunucu olarak sürülebilir |
| Dia (Atlassian) | Bağımsız | 14 gün deneme | Tam | macOS; bilgi çalışanı odaklı |
| Fellou | Bağımsız | — | Tam | Plan şeffaflığı (yürütmeden önce akış düzenlenir) |
| Genspark | Bağımsız | Kısmen | Tam (Autopilot) | On-device modeller |
| Sigma AI | Bağımsız | Evet | Tam | Gizlilik-öncelikli |
| Samsung Browser | Windows+Android | Evet | Tam | Perplexity motorlu |
| Edge (gömülü AI) | Windows/Android | Evet | Kısmi | Copilot Mode markası Mayıs 2026'da emekli |
| Brave Leo | Brave içinde | Evet | Yok | Yerel depolama, BYOM |
| ChatGPT Atlas | **KAPANDI (Ağu 9, 2026)** | — | — | ChatGPT for browser içine katlandı |
| Lightpanda (bizim motor) | Bağımsız motor (bağlantı katmanı) | OSS | Motor | C2/C3'ün **çalıştırdığı** katmandır — biz onların altındayız |

### C4. Ajan-otomasyon çerçeveleri (tarayıcıyı sürerler)
Browser Use (OSS), Stagehand (Browserbase), Vercel agent-browser (`@e1` referansları, ~%93 token tasarrufu — satıcı beyanı), Playwright MCP, Puppeteer, Selenium, Firecrawl `/agent`+`/interact`, Steel leaderboard ajanları.

### Pazar gerçeği
Piyasa iki eksende ayrışıyor: (1) **geçme/stealth** (bot-korumalı siteler) — burada çizgimiz: bir reddi **gizlice atlatmayız, açıkça bildiririz** (`robots_disallowed`, `blocked_by_site`, `captcha_required`, `paywall_or_login_required`, `rate_limited_by_site`; bkz. product-skeleton §3a). Yine de gerçek tarayıcının yaptığı iki meşru kanal sunarız: (a) **`user_directed` modu** — kullanıcı tek URL'yi kendi oturumuyla açıkça istediğinde robots.txt not olarak geçer (otomatik crawl'da robots'a uyulur); (b) **kullanıcı oturumu** (kendi hesabını secret-vault ile bağlar) — site kullanıcıyı tanıdığından içerik zaten açıktır. İkisinde de `captcha_required`/`paywall_or_login_required` asla çözülmez, bildirilir. Yasağı aşmak değil, kullanıcının kendi erişim hakkını kullanması hedeflenir. (2) **maliyet + hız + hafiflik** — burası bizim asıl alanımız (self-host, ~17 MiB, ~20 ms). Biz C2/C3'ün "

## 5. Kaynaklar
- Firecrawl vs Jina Reader 2026 — use-apify.com/blog/firecrawl-vs-jina-reader-2026
- 8 Best Web Scraping APIs 2026 — firecrawl.dev/blog/best-web-scraping-api
- Best Web Scraping APIs 2026 (fiyatlar, Eylül 2026) — pagecrawl.io/blog/best-web-scraping-apis-2026
- Top 11 Web Scraping APIs for AI 2026 — context.dev/blog/top-10-web-scraping-apis-for-ai
- The 7 best web scraping APIs for AI 2026 — spider.cloud/blog/best-web-scraping-apis-for-ai-2026/
- 11 Best AI Browser Agents 2026 — firecrawl.dev/blog/best-browser-agents
- Browser Run for AI Agents — blog.cloudflare.com/browser-run-for-ai-agents
- 9 Best AI Agent Browser Infrastructure Platforms (Ekim 2026) — mastra.ai/articles/best-ai-agent-browser-infrastructure-platforms
- Agent-Browser (Vercel Labs) — medium.com/@richardhightower/agent-browser-…
- WebMCP — javascript-conference.com/blog/webmcp-ai-agents-web-apps/
- Cloud Browsers for AI Agents (Stealth Bench V2, fiyat/oturum açma) — browser-use.com/cloud-browsers
- Anchor Browser Alternatives 2026 (bulut altyapı detayları) — o-mega.ai/articles/top-10-anchor-browser-alternatives-2026
- Browserbase Alternatives 2026 (fiyatlar, yetenekler) — simular.ai/alternatives/browserbase-alternatives
- 7 Best Cloud Browsers for AI Agents 2026 (katman tanımı) — proxidize.com/blog/best-cloud-browsers-for-ai-agents
- Agentic Browser Landscape 2026 (zaman çizelgesi, AI tarayıcıları) — nohacks.co/blog/agentic-browser-landscape-2026
- AI Web Browsers Selection Guide (Atlas/Comet/Neon) — aimultiple.com/ai-web-browser
- What Is an Agentic Browser? 2026 — sigmabrowser.com/blog/what-is-an-agentic-browser-best-agentic-browsers-in-2026
