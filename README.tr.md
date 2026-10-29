# Pergel

**Yapay zekâ çağı için geliştirilmiş, gizliliğe saygılı, telemetrisiz, açık kaynak masaüstü tarayıcı.**

Pergel verinizi asla satmaz, arka planda asla eve telefon etmez, sizi tek bir motora ya da modele
mahkûm etmez. **BYOK (Bring Your Own Key — Kendi Anahtarını Getir)** felsefesiyle çalışır:
kendi yapay zekâ sağlayıcı anahtarınızı girersiniz, istekleriniz doğrudan o sağlayıcıya gider.
Bakiye tutan ya da istemlerinizi okuyan bir aracı yoktur.

[English](README.md) | **Türkçe**

- **Telemetri yok.** Arka planda veri akışı yok, kullanıcı satışı yok, reklam profilleme yok.
- **BYOK.** Kendi API anahtarınızı getirin (OpenRouter, Nous, Ollama ve daha fazlası).
- **Açık kaynak ve ücretsiz.** Abonelik kademesi yok, ücretli özellik yok.

---

## Bu depo insanlar kadar AI ajanları için de düzenlendi

Bu depo, bir yapay zekâ ajanının hızla devreye girebilmesi için düzenlendi. Bir ajan burada
çalışmaya başlarken önce şu dosyaları okur:

| Dosya | Amaç |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Depo içi ajan politikası: komutlar, kurallar, doğrulama |
| [`llms.txt`](llms.txt) | Bağlantı öncelikli dokümantasyon haritası |
| [`CODEBASE_GRAPH.json`](CODEBASE_GRAPH.json) | AST tabanlı kod grafiği — tek tek dosya açmadan gezinme |

Kural: koddan önce `CODEBASE_GRAPH.json`, kural ve komutlar için `AGENTS.md` okunur.

---

## Kurulum

İki desteklenen yol. Size hangisi uyuyorsa onu seçin — ikisi de birinci sınıf.

### A) Manuel kurulum (insanlar için)

**1 · Kodu alın**

```bash
git clone https://github.com/sametatakan0000-netizen/pergel.git
cd pergel
```

**2 · Gereksinimler** — Python **3.10+** ve Chromium ailesi bir tarayıcı.

```bash
sudo apt update
sudo apt install -y python3 python3-venv chromium-browser   # veya google-chrome-stable
```

**3 · Python bağımlılıkları**

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

**4 · Masaüstü uygulaması (önerilen)** — Debian paketini derleyip kurun:

```bash
PYTHONPATH=. python3 -c "from src.brand.package import build_deb; print(build_deb('dist'))"
sudo apt install -y ./dist/pergel-browser_*.deb
```

Bu, `pergel` komutunu `/usr/bin/pergel` içine ve uygulama menüsüne kurar. Sonra uygulama
menüsünden **Pergel**'i başlatın ya da terminalde `pergel` komutunu çalıştırın.

**5 · Çalıştığını doğrulayın**

```bash
pergel --help                       # uygulama açılır
python3 -m unittest discover -s tests -t .   # test paketi yeşildir
```

<details>
<summary><b>Debian/Ubuntu değil mi? Kaynaktan çalıştırın</b></summary>

Kaynak düz Python olduğu için `.deb` olmadan da çalışır:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python3 -m src.cli doctor   # sağlık kontrolü
```

Windows (PowerShell) için: `py -3 -m venv .venv`, sonra `.venv\Scripts\Activate.ps1`, sonra aynı
`pip install`. Her yerde `.deb` üretmek için (Debian, Ubuntu, Mint, Pop!_OS, Kali, MX...) 4.
adımdaki `build_deb` komutunu kullanın.
</details>

### B) Bir yapay zekâ ajanıyla kurulum (Claude Code, Codex, OpenCode, Hermes...)

Kurulumu bir yapay zekâ ajana yaptırmak isterseniz bu depoyu ve şu talimatı verin.
Kopyala-yapıştır istem:

> `https://github.com/sametatakan0000-netizen/pergel.git` deposunu klonla ve bu makineye kur.
> Önce `AGENTS.md` ve `llms.txt` dosyalarını oku, sonra `README.tr.md` içindeki **Manuel kurulum**
> adımlarını sırasıyla izle. Virtualenv kullan, asla `sudo pip install` yapma. `.deb` derlersen
> `sudo apt install -y ./dist/pergel-browser_*.deb` ile kur. Sonra
> `python3 -m unittest discover -s tests -t .` çalıştır ve sonucu göster. Depo dışında hiçbir
> dosyayı değiştirme ve `sudo` içeren her komuttan önce bana sor.

---

## Pergel neden var (proje geçmişi ve yapay zekâ vizyonu)

Bu proje tek bir gözlemden yola çıktı; arkasında depoda duran pazar araştırması var
(`docs/product/market-landscape_2026-10-26.md`, `docs/rea/ai-browsers.md`):

**Yapay zekânın en zayıf yeri sohbet değil, internette gezinmektir.** Bir yapay zekâ ajanı
gezinirken karmaşık DOM üzerinde jeton yakar, sayfa yapısını tahmin eder ve aslında pek
ihtiyacı olmadığı ağır sayfaların tam fiyatını öder. Piyasadaki "yapay zekâ tarayıcı"ların çoğu
arama motoruna eklenmiş bir cevap kutusudur.

Baştan çözmeye çalıştığımız dört şey:

1. **Yapay zekâ iyi ve ucuz gezinmeli.** Çok katmanlı motor merdiveni ucuz sayfayı ucuz bırakır
   (aşağıdaki ölçümler).
2. **Yapay zekâ modu ≠ yapay zekâ araması.** Fark gerçek ve mesele bu — aşağıda.
3. **Gizlilik, pazarlık dışı.** Veri satışı yok, telemetri yok, arka planda senkronizasyon yok.
4. **Şatafattan değil, dürüstlükten.** Buradaki her sayı ham ölçüm dosyasıyla dayanaklanır.

### Yapay zekâ modu ile klasik yapay zekâ araması arasındaki fark

Pazar araştırması yapay zekânın web erişimini dört kategoriye ayırıyor: **(A)** okuma/Markdown
API'leri, **(B)** arama + içerik, **(C)** uzak tarayıcı / tarayıcı ajanı, **(D)** ajan-yerel
yüzeyler (WebMCP). Klasik "yapay zekâ araması" **B**'de yaşar — cevap üretir, ya güvenirsiniz
ya güvenmezsiniz.

| | Klasik yapay zekâ araması | Pergel'in yapay zekâ modu |
|---|---|---|
| Çıktı | Tek üretilmiş cevap | Alt sorgular + **tıklanabilir alıntılar** |
| Dayanak | Model belleği + snippet | Gerçek çekilmiş sayfalar |
| Maliyet | Ağır sayfada tam fiyat | Ucuz sayfa ucuz kalır (motor merdiveni) |
| Şeffaflık | "Bana güven" | Her iddia bir kaynağı işaret eder |

Üründeki karşılıkları:

- **Sorgu Fan-Out** (`/v1/search/fanout`) — tek bir soru birkaç alt sorguya dönüşür, sonuçlar
  **satır içi alıntılarla** cevaplanır. Uydurma değil, dayanaklı cevap.
- **Motor merdiveni** — hafif sayfa hafif motorla, JS-ağır sayfa tam Chromium'a çıkar.
- **Yerleşik engelleme** — **92.000+ kural, MV3 kotası olmadan** kural motoru.
- **Ajan-dostu arayüz** — REST API + **MCP sunucusu** + CLI + CDP.

Bilinmesi gereken bir şey daha: **istem enjeksiyonu 2026'da çözülmüş değil** (sayfaların içine
gizlenmiş talimatlar ajanları kandırıyor). Bizim cevabımız ilk günden tasarlandı: ayrı profil
izolasyonu + onay kapısı + içerik talimatı filtresi.

---

## Pergel neleri karşılar (dürüst rekabet tablosu)

Ekim 2026'da araştırıldı (kaynaklar `docs/rea/ai-browsers.md` ve
`docs/product/market-landscape_2026-10-26.md`). Marka adları sahiplerine aittir; bu bir
tanımlayıcı pazar bağlamıdır, karşılaştırma ölçümü değil.

| Ürün | Motor | Ajan | Platformlar | Fiyat |
|---|---|---|---|---|
| Perplexity Comet | Chromium | var (kotalı) | Win/mac/iOS/Android | ücretsiz; Pro $20 |
| ChatGPT Atlas *(08/2026'da kapandı)* | Chromium | var | macOS | — |
| Chrome + Gemini | Chromium | var (ABD, ücretli) | hepsi | $19.99+ |
| Edge + Copilot | Chromium | var (ABD) | hepsi | ücretsiz / M365 |
| Opera Neon | Chromium | var ($19.90) | Win/mac | ücretli |
| Fellou / Genspark / BrowserOS | Chromium | var | Win/mac | ücretsiz–$25 |
| **Pergel** | Chromium + hafif çekirdek motor | var (yerel, BYOM) | **Linux paketi; platformlar arası çekirdek** | **sonsuza dek ücretsiz** |

**Kazandığımız yerler (dürüst):** hızlı ve hafif çekirdek katmanı, MV3'te bozulmayan engelleme,
alıntılı cevaplar, sıfır telemetri, temiz otomasyon yüzeyi. **Kaybettiğimiz yerler (dürüst):**
hazır kullanıcı tabanı yok, kendi modelimiz yok, eklenti mağazası paritesi yok. Analiz
[`docs/rea/positioning-synthesis.md`](docs/rea/positioning-synthesis.md) içinde.

---

## Ölçümler — ne ölçtük

> **Kapsam:** bu sayılar Pergel'in **otomasyon/çekme katmanını** ölçer. Pergel'in günlük masaüstü
> gezinmesi **Chromium tabanlıdır**; aşağıdaki ms değerleri sekme hızınız değil, arka plan
> çekme/otomasyon hızıdır.

`src/bench/run.py` ile deterministik yerel sunucuya karşı ölçüldü. Her hücre **10 bağımsız
yaşam döngüsü** (her seferinde yeni süreç), medyan + **%95 bootstrap güven aralığı**. Donanım:
13. Nesil Intel Core i5-13420H (12 çekirdek), çekirdek 7.0.0-38. Her sayı ham ölçüm dosyasıyla
dayanaklanır. **Pergel** satırları bizim motor katmanlarımız; `*(ref)*` satırları sadece
karşılaştırma referansı olan bağımsız tarayıcılardır.

**Senaryolar:** `static` — düz HTML. `spa` — JavaScript ile sürülen sayfa (JS çalışmalı).
`heavy` — çok kaynaklı ağır sayfa (stres testi).

### Hız — sıcak çekme medyanı (ms, düşük daha iyi)

| Motor | static | spa | heavy |
|---|---|---|---|
| **Pergel · çekme motoru** (lightpanda) | **19.8** | **63.5** | **25.0** |
| **Pergel · masaüstü motoru** (Chromium) | 112.6 | 155.2 | 119.9 |
| chrome-headless-shell *(ref)* | 44.4 | 86.6 | 51.4 |
| playwright-chromium *(ref)* | 44.6 | 87.5 | 51.8 |
| edge *(ref)* | 99.0 | 141.3 | 111.7 |
| brave *(ref)* | 103.3 | 147.6 | 113.2 |
| firefox-pw *(ref)* | 176.8 | 236.5 | 194.1 |
| webkit-pw *(ref)* | 203.4 | 237.8 | 228.5 |

### Bellek — zirve PSS (MiB, düşük daha iyi)

| Motor | static | spa | heavy |
|---|---|---|---|
| **Pergel · çekme motoru** (lightpanda) | **23.1** | **24.2** | **23.7** |
| **Pergel · masaüstü motoru** (Chromium) | 479.5 | 501.3 | 500.6 |
| chrome-headless-shell *(ref)* | 175.0 | 174.6 | 160.8 |
| playwright-chromium *(ref)* | 176.0 | 175.2 | 159.3 |
| webkit-pw *(ref)* | 194.3 | 197.5 | 207.3 |
| brave *(ref)* | 325.6 | 354.1 | 366.4 |
| firefox-pw *(ref)* | 506.8 | 511.5 | 508.6 |
| edge *(ref)* | 508.1 | 513.8 | 493.9 |

### Soğuk başlangıç (ms, düşük daha iyi)

| Motor | static | spa | heavy |
|---|---|---|---|
| **Pergel · çekme motoru** (lightpanda) | 244.0 | 244.4 | 242.7 |
| **Pergel · masaüstü motoru** (Chromium) | 365.1 | 361.3 | 367.2 |
| playwright-chromium *(ref)* | 261.8 | 267.6 | 263.9 |
| chrome-headless-shell *(ref)* | 264.7 | 262.8 | 264.4 |
| webkit-pw *(ref)* | 266.4 | 258.5 | 256.5 |
| brave *(ref)* | 363.6 | 364.1 | 363.2 |
| edge *(ref)* | 426.9 | 423.1 | 420.0 |
| firefox-pw *(ref)* | 442.2 | 435.8 | 447.9 |

**Düz Türkçesi:** Pergel'in çekme katmanı (lightpanda) en yakın Chromium tabanlı hedeften
yaklaşık **2 kat hızlı** ve **~10 kat hafif**. Otomasyon ve tarama işlerinde bu doğrudan bir
**işletme maliyeti** avantajıdır. (Masaüstü motoru tam Chromium'dur — günlük gezinirken
kullandığınız katman budur; bellek maliyeti gerçek bir tarayıcının ödediğidir.)

**Başarı oranı:** her motor üç senaryoda da çekmelerinin **%100'ünü** tamamladı. `vivaldi`
hedefi **`BLOCKED`** olarak işaretlendi: headless'te CDP bağlantı noktasını açmadığı için bu
makinede ölçülemez. Sayı uydurmak yerine ölçülemez olarak işaretliyoruz.

*13. Nesil Intel(R) Core(TM) i5-13420H (12 çekirdek), çekirdek 7.0.0-38-generic, yük 0.57, git `0a56efd`, 2026-10-28.*
*Yöntem: örnekleme birimi, yaşam döngüsü başına sıcak çekme medyanıdır; GA'lar %95 bootstrap'tir.*

Her hücre ham ölçüm verisiyle dayanaklanır:
[`bench/results/20261028-200116_full9/raw.jsonl`](bench/results/20261028-200116_full9/raw.jsonl).

**Bilerek kaçındığımız iddialar:** "Pergel en hızlı tarayıcıdır", "her kullanımda hızlıdır"
ya da mutlak ms garantisi. Bu ölçüm bunları desteklemiyor. `lightpanda` Pergel'in çekme
katmanı olarak kullanılan üçüncü taraf (AGPL) bir motordur.

---

## İşletim sistemi desteği

Pergel'in çekirdeği platform kodu içermeyen düz Python 3.10+'tır — Python olan her yerde çalışır.
Platforma özgü olan paketlemedir.

| Platform | Çekirdek (motor, router, API, MCP, CLI) | Masaüstü paketi | Hafif çekme motoru |
|---|---|---|---|
| **Debian / Ubuntu** ve türevleri | evet | evet `.deb` + uygulama menüsü | evet |
| Diğer Linux | evet | kaynaktan çalıştırma | evet |
| macOS | evet | kaynaktan çalıştırma | evet |
| Windows | evet | kaynaktan çalıştırma | hayır (Chromium'a düşer) |

Windows'ta motor merdiveni otomatik olarak Chromium'a düşer — hiçbir şey bozulmaz, sadece hafif
motoru almazsınız.

---

## Nereden geldik (proje tarihi)

Açık ve sürekli geliştirildi — gerçek iş, sırasıyla (tam liste: `git log`):

- **Araştırma odaklı başlangıç** — motor SOTA taraması ve yazılı mimari kararı.
- **Üç motorlu test kampanyası** — Chrome-CFT + Chromium + Lightpanda, 138 taze süreç.
- **Rekabet ölçümü** — bootstrap güven aralıkları, Vivaldi için dürüst `BLOCKED` işareti.
- **Güvenlik katmanı** — Chromium ağ ad alanı, SSRF koruması, yönlendirme kontrollü çıkış proxy'si.
- **Eklenti platformu** — MV3 kural yüzeyi + yalıtılmış eklenti host'u.
- **Platform adaptörleri** — oEmbed, YouTube transkriptleri, RSS/Atom, Wayback, Reddit OAuth.
- **Derin sertleştirme** — DNS-rebinding koruması, IP sabitleme, TLS doğrulama.
- **Yapay zekâ modu** — fan-out + alıntılar, REST API, MCP sunucusu, LiveRouter + model kaydı.
- **Küresel öncelik** — 8 dil, RTL, erişilebilirlik.
- **Kimlik** — tam marka yenileme (Vane → Pergel), ikonlar, `.deb` masaüstü paketi.
- **Bu README** — okunabilir ölçüm tabloları, çift kurulum rehberi ve dürüst eksikler.

---

## Dürüst eksikler (henüz olmayanlar)

`docs/product/market-landscape_2026-10-26.md` ve `docs/product/human-face-review_2026-10-26.md`
içinde belgelendi — şimdi bilmeniz, sonra fark etmenizden iyidir:

1. **Oturum kayıt/tekrar, Canlı Görünüm** — henüz yok.
2. **WebMCP** — henüz yok (Chromium 146+ gerektirir).
3. **Anti-bot / CAPTCHA / konut proxy'si** — bilerek kapsam dışı. Bot duvarlarını ve ödeme
   duvarlarını aşmak için gizlilik/dolandırıcılık önleme teknikleri geliştirmiyoruz.
4. **Windows/macOS yerel paketleme** — kaynaktan çalışır; yükleyici yok.

Yakında çıkanlar (önceden eksikler listesindeydi):
- **Web arayüzü** — `http://127.0.0.1:8871/ui/` — `/start`, `/history`, `/settings` sekmeleri.
- **Tarama / site haritası** — `/v1/crawl` (toplu çekme + çıkarma, en fazla 50 paralel) ve
  `/v1/map` (sitemap tabanlı URL keşfi).
- **Şema tabanlı JSON çıkarma** — `/v1/extract` (JSON-LD, CSS seçiciler, regex).
- **Yapılandırılmış hata zarfı** — her API yanıtında `request_id` korelasyonu.

---

## Dürüstlük notu

Bu depodaki performans sayıları yalnızca yeniden üretilebilir ölçüm çıktısıyla
(`bench/results/`) birlikte yayınlanır. Ham ölçümü olmayan rakip satırlar bilerek
atlanır ya da `BLOCKED` olarak işaretlenir — asla tahminle doldurulmaz. Pazarlama kuralı:
"ölçtüğünle konuş, abartma."

Pergel'in olmadıkları: bitmiş ticari tarayıcı. Aktif geliştirilen, işe yarar açık kaynak
tarayıcı + motor. Masaüstü deneyimi Chromium tabanlıdır; otomasyon/çekme katmanı yukarıdaki
ölçümlerin konusudur.

---

## Geliştirme

```bash
# test paketi (yeşil olmalı)
python3 -m unittest discover -s tests -t .

# kod grafiğini yenile
PYTHONPATH=. python3 -m src.cli graph

# doctor + güvenlik/borç denetimi
PYTHONPATH=. python3 -m src.cli doctor
```

Tüm kurallar ve komutlar için [`AGENTS.md`](AGENTS.md) dosyasına bakın.

---

## Lisans

Kod üçüncü taraf bileşen lisanslarına tabidir (Chromium tabanlı kabuk BSD-3-Clause, otomasyon
motoru AGPL-3.0 ve diğerleri). Bkz. [`LICENSE`](LICENSE) ve `docs/rea/` altındaki bileşen
notları.

## Destek

Pergel sonsuza dek ücretsiz kalacak. Geliştirmenin sürmesini isterseniz
[GitHub Sponsors](https://github.com/sponsors/sametatakan0000-netizen) üzerinden
destekleyebilirsiniz.

---

*Açık kaynak. Gizlilik öncelikli. İnsanlar ve ajanlar için.*
