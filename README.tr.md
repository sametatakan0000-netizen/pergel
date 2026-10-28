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

## Hız / bellek ölçümü — dürüst okuma

> **Önemli:** Aşağıdaki rakamlar ürünün **otomasyon/fetch katmanını** ölçer — yani
> programatik sayfa çekme motorunu. Pergel'in masaüstü gezinme deneyimi **Chromium
> tabanlıdır**; buradaki ms değerleri günlük sekme hızınızı değil, headless
> fetch/otomasyon performansını temsil eder.

`src/bench/run.py` harness'ı ile, deterministik yerel fixture sunucusunda, her hücre
10 bağımsız yaşam döngüsü (taze süreç) ve %95 bootstrap CI ile ölçüldü. Ölçüm
donanımı: 13th Gen Intel Core i5-13420H (12 çekirdek), kernel 7.0.0-38, load 0.57.
**Yalnızca ham ölçümü depoda (`bench/results/*/raw.jsonl`) bulunan hedefler raporlanır.**

### Hız — sıcak fetch medyanı (ms, düşük daha iyi)

| Hedef | static | spa | heavy |
|---|---|---|---|
| brave | 103.3 | 147.6 | 113.2 |
| chrome-cft | 112.6 | 155.2 | 119.9 |
| chrome-headless-shell | 44.4 | 86.6 | 51.4 |
| edge | 99.0 | 141.3 | 111.7 |
| firefox-pw | 176.8 | 236.5 | 194.1 |
| lightpanda | **19.8** | 63.5 | 25.0 |
| playwright-chromium | 44.6 | 87.5 | 51.8 |
| webkit-pw | 203.4 | 237.8 | 228.5 |

### Bellek — peak PSS (MiB, düşük daha iyi)

| Hedef | static | spa | heavy |
|---|---|---|---|
| brave | 325.6 | 354.1 | 366.4 |
| chrome-cft | 479.5 | 501.3 | 500.6 |
| chrome-headless-shell | 175.0 | 174.6 | 160.8 |
| edge | 508.1 | 513.8 | 493.9 |
| firefox-pw | 506.8 | 511.5 | 508.6 |
| lightpanda | **23.1** | 24.2 | 23.7 |
| playwright-chromium | 176.0 | 175.2 | 159.3 |
| webkit-pw | 194.3 | 197.5 | 207.3 |

**Doğru okuma:** fetch katmanı (lightpanda) en yakın Chromium tabanlı headless
hedefe göre ~2× daha hızlı ve ~10× daha hafif ölçüldü. Bu, otomasyon/crawler
için doğrudan **çalıştırma maliyeti** avantajıdır.

**Kaçınılacak iddialar:** "Pergel en hızlı tarayıcı", "tüm kullanımlarda hızlı",
mutlak ms garantisi. Bunlar bu ölçümle desteklenmez. lightpanda üçüncü taraf
(AGPL) bir motordur; Pergel'in kendi motoru değildir, yalnızca fetch/otomasyon
katmanında kullanılır.

**Dürüstlük notu:** `vivaldi` bu donanımda ölçülemez (headless CDP portunu açmıyor);
harness onu `BLOCKED` olarak işaretleyip atlar — uydurma rakam yazılmaz. Tüm
rakamlar `bench/results/20261028-200116_full9/raw.jsonl` ile desteklidir.

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
