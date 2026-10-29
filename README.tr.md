# Pergel

**Gizliliğe saygılı, telemetrisiz, yapay zekâ için tasarlanmış açık kaynak masaüstü tarayıcı.**

Pergel; veri satmayan, arka planda telefon etmeyen, kendi motorunu ya da modelini
size dayatmayan bir tarayıcıdır. BYOK (Bring Your Own Key) felsefesiyle çalışır:
AI sağlayıcı anahtarınızı siz girersiniz, istekleriniz doğrudan o sağlayıcıya gider.
Arada bakiye toplayan, prompt'unuzu gören bir aracı yoktur.

- **Telemetri yok.** Arka plan veri akışı, kullanıcı satışı, reklam profillemesi yok.
- **BYOK.** Kendi API anahtarınızı (OpenRouter, Nous, Ollama vb.) siz girersiniz.
- **Açık kaynak.** Ücretsiz, abonelik paketi yok.

---

## AI için tasarlanmış bir depo

Bu depo insanlar kadar **yapay zekâ ajanları için** de düzenlidir. Bir ajan bu depoda
çalışmaya başladığında önce şu dosyaları okur:

| Dosya | Ne için |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Depo içi ajan yönergesi: komutlar, kurallar, doğrulama |
| [`llms.txt`](llms.txt) | Dokümantasyonun link-öncelikli haritası |
| [`CODEBASE_GRAPH.json`](CODEBASE_GRAPH.json) | AST tabanlı kod grafiği — tek tek dosya açmadan gezinme |

Kural: kodu okumadan önce `CODEBASE_GRAPH.json`, kural ve komutlar için `AGENTS.md`.

---

## Kurulum

İki desteklenen yol var. Size hangisi uyuyorsa onu seçin — ikisi de birinci sınıf.

### A) Manuel kurulum (insaneler için)

**1 · Kodu alın**

```bash
git clone https://github.com/sametatakan0000-netizen/pergel.git
cd pergel
```

**2 · Gereksinimler** — Python **3.10+** ve Chromium ailesinden bir tarayıcı.

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

Bu komut `pergel`'i `/usr/bin/pergel`'e ve menüye ekler. Ardından uygulama
menüsünden **Pergel**'i başlatın ya da terminalde `pergel` yazın.

**5 · Çalıştığını doğrulayın**

```bash
pergel --help                       # uygulama başlıyor
python3 -m unittest discover -s tests -t .   # test paketi yeşil
```

<details>
<summary><b>Debian/Ubuntu değil mi? Herhangi bir dağıtımda paket derleyin</b></summary>

Kaynak düz Python olduğu için `.deb` olmadan da çalıştırabilirsiniz:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python3 -m src.cli doctor   # sağlık kontrolü
```

`dpkg-deb`'in olduğu her yerde (Debian, Ubuntu, Mint, Pop!_OS, Kali, MX…) `.deb`
üretmek için 4. adımdaki aynı `build_deb` komutunu kullanın.
</details>

### B) Yapay zekâ ajanıyla kurulum (Claude Code, Codex, OpenCode, Hermes…)

Kurulumu bir yapay zekâ ajanına yaptırmak isterseniz, ona bu depoyu ve şu talimatı
verin. Kopyala-yapıştır komut:

> `https://github.com/sametatakan0000-netizen/pergel.git` deposunu klonlayıp bu
> makineye kur. Önce `AGENTS.md` ve `llms.txt` dosyalarını oku, sonra
> `README.tr.md` içindeki **Manuel kurulum** adımlarını (1–5) sırayla uygula.
> Sanal ortam (venv) kullan, asla `sudo pip install` yapma. `.deb` derlersen
> `sudo apt install -y ./dist/pergel-browser_*.deb` ile kur. Sonra
> `python3 -m unittest discover -s tests -t .` çalıştır ve sonucu göster. Depo
> dışındaki hiçbir dosyayı değiştirme, `sudo` içeren her komuttan önce bana sor.

Neden işe yarıyor: bu depo **ajan-dostu**. Ajan tahminle gezinmez, üç hazır
giriş noktasından birini okur:

| Dosya | Ajana sağladığı |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Komutlar, kurallar ve "yapıldı iddiası kanıt ister" kuralı |
| [`llms.txt`](llms.txt) | Dokümantasyonun link-öncelikli haritası |
| [`CODEBASE_GRAPH.json`](CODEBASE_GRAPH.json) | AST kod grafiği — tek tek dosya açmadan gezinme |

Güvenli kuran üç kural: **(1)** ajan koda dokunmadan önce `AGENTS.md` okur;
**(2)** asla sonuç uydurmaz — ölçülmeyen olmamıştır; **(3)** `sudo` yalnızca
`.deb` kurulumunda ve sadece size sorduktan sonra.

---

## Benchmark — neyi ölçtük

> **Kapsam:** bu rakamlar ürünün **otomasyon/fetch katmanını** ölçer — yani
> programatik sayfa çekme motorunu. Pergel'in günlük masaüstü gezinmesi
> **Chromium tabanlıdır**; aşağıdaki ms değerleri sekme hızınız değil, headless
> fetch/otomasyon hızıdır.

`src/bench/run.py` ile deterministik yerel bir sunucuda ölçüldü. Her hücre
**10 bağımsız yaşam döngüsü** (her seferinde taze süreç) ve medyan ile **%95
bootstrap güven aralığı** içerir. Donanım: 13th Gen Intel Core i5-13420H (12
çekirdek), kernel 7.0.0-38. Aşağıdaki her rakam en altta bağlantısı verilen ham
ölçüm dosyasıyla desteklidir — burada tahmin yoktur.

**Üç senaryo nasıl okunur:**
- `static` — düz HTML sayfası. En basit durum.
- `spa` — JavaScript ile çalışan tek sayfalık uygulama. Motor JS çalıştırıp beklemeli.
- `heavy` — çok sayıda kaynağı olan büyük sayfa. Stres testi.

### Hız — sıcak fetch medyanı (ms, düşük daha iyi)

| Motor | static | spa | heavy |
|---|---|---|---|
| **lightpanda** | **19.8** | **63.5** | **25.0** |
| chrome-headless-shell | 44.4 | 86.6 | 51.4 |
| playwright-chromium | 44.6 | 87.5 | 51.8 |
| edge | 99.0 | 141.3 | 111.7 |
| brave | 103.3 | 147.6 | 113.2 |
| chrome-cft | 112.6 | 155.2 | 119.9 |
| firefox-pw | 176.8 | 236.5 | 194.1 |
| webkit-pw | 203.4 | 237.8 | 228.5 |

### Bellek — peak PSS (MiB, düşük daha iyi)

| Motor | static | spa | heavy |
|---|---|---|---|
| **lightpanda** | **23.1** | **24.2** | **23.7** |
| chrome-headless-shell | 175.0 | 174.6 | 160.8 |
| playwright-chromium | 176.0 | 175.2 | 159.3 |
| webkit-pw | 194.3 | 197.5 | 207.3 |
| brave | 325.6 | 354.1 | 366.4 |
| chrome-cft | 479.5 | 501.3 | 500.6 |
| firefox-pw | 506.8 | 511.5 | 508.6 |
| edge | 508.1 | 513.8 | 493.9 |

### Soğuk başlangıç (ms, düşük daha iyi)

| Motor | static | spa | heavy |
|---|---|---|---|
| lightpanda | 244.0 | 244.4 | 242.7 |
| playwright-chromium | 261.8 | 267.6 | 263.9 |
| chrome-headless-shell | 264.7 | 262.8 | 264.4 |
| webkit-pw | 266.4 | 258.5 | 256.5 |
| brave | 363.6 | 364.1 | 363.2 |
| chrome-cft | 365.1 | 361.3 | 367.2 |
| edge | 426.9 | 423.1 | 420.0 |
| firefox-pw | 442.2 | 435.8 | 447.9 |

**Düz okunuşu:** bu ölçümede fetch katmanı (`lightpanda`) en yakın Chromium
tabanlı headless hedefe göre kabaca **2× daha hızlı** ve **~10× daha hafif**.
Otomasyon ve tarama iş yükleri için bu doğrudan **çalıştırma maliyeti**
avantajıdır: aynı makine, aynı bellekle çok daha fazla paralel oturum kaldırır.

**Başarı oranı:** yukarıdaki her motor üç senaryonun tamamında çekimlerinin
**%100**'ünü tamamladı. `vivaldi` adlı hedef **`BLOCKED`** olarak görünüyor:
headless modda CDP DevTools portunu hiç açmıyor, bu yüzden bu donanımda
ölçülemiyor. Uydurma bir rakam yazmak yerine ölçülemez olarak işaretliyoruz.

*13th Gen Intel(R) Core(TM) i5-13420H (12 çekirdek), kernel 7.0.0-38-generic, load 0.57, git 0a56efd, 2026-10-28 tarihinde çalıştırıldı.*
*Yöntem: örnek birimi, sıcak fetch'lerin yaşam döngüsü medyanıdır; GA'ler %95 bootstrap'tir; gecikme oranı yalnızca GA'lar çakışmadığında iddia edilir (n≥10 yaşam döngüsü). Gecikme yalnızca başarılı fetch'leri karşılaştırır.*

**Kasıtlı olarak kaçındığımız iddialar:** "Pergel en hızlı tarayıcı", "her
kullanımda hızlı" ya da mutlak ms garantisi. Bu ölçüm bunları desteklemiyor.
`lightpanda` Pergel'in kendi motoru değil, üçüncü taraf (AGPL) bir motordur;
yalnızca fetch/otomasyon katmanında kullanılır.

Her hücre ham ölçüm verisiyle desteklidir:
[`bench/results/20261028-200116_full9/raw.jsonl`](bench/results/20261028-200116_full9/raw.jsonl).

---

## Dürüstlük notu (şeffaflık)

Bu depodaki performans rakamları yalnızca **yeniden üretilebilir** ölçüm
çıktılarıyla (`bench/results/`) yayınlanır. Ölçülmediği halde tabloya giren
rakip satırları (Brave, Edge, WebKit gibi) bilinçli olarak çıkarılmıştır; çünkü
bunların ham ölçümü depoda yoktur. Pazarlama dilinde "ölçülenle konuş, abartma"
kuralı geçerlidir.

---

## Geliştirme

```bash
# test suite (100% yeşil olmalı)
python3 -m unittest discover -s tests -t .

# kod grafiğini tazele
PYTHONPATH=. python3 -m src.cli graph

# doktor + güvenlik/borç denetimi
PYTHONPATH=. python3 -m src.cli doctor
```

Kurallar ve tam komutlar için [`AGENTS.md`](AGENTS.md).

---

## Lisans

Kod, üçüncü taraf bileşenlerin lisanslarına tabidir (Chromium tabanlı kabuk BSD-3-Clause,
otomasyon motoru AGPL-3.0 vb.). Ayrıntılar için [`LICENSE`](LICENSE) ve
`docs/rea/` altındaki bileşen notlarına bakın.

## Destek

Pergel ücretsiz kalacak. Geliştirmeyi sürdürmek isterseniz
[GitHub Sponsors](https://github.com/sponsors/sametatakan0000-netizen) üzerinden
destekleyebilirsiniz.
