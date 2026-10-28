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
donanımı: 13th Gen Intel Core i5-13420H (12 çekirdek), kernel 7.0.0-38.
**Yalnızca ham ölçümü depoda (`bench/results/*/raw.jsonl`) bulunan hedefler raporlanır.**

### Hız — sıcak fetch medyanı (ms, düşük daha iyi)

| Hedef | static | spa | heavy |
|---|---|---|---|
| lightpanda | **18.7** | **62.9** | **24.0** |
| chrome-headless-shell | 41.8 | 84.0 | 49.2 |
| playwright-chromium | 42.5 | 85.0 | 49.8 |
| chrome-cft | 101.0 | 146.6 | 111.1 |
| firefox-pw | 164.5 | 226.1 | 179.4 |

### Bellek — peak PSS (MiB, düşük daha iyi)

| Hedef | static | spa | heavy |
|---|---|---|---|
| lightpanda | **17.3** | **17.2** | **17.2** |
| chrome-headless-shell | 87.1 | 86.8 | 87.1 |
| playwright-chromium | 172.0 | 172.3 | 171.6 |
| chrome-cft | 298.9 | 301.3 | 298.9 |
| firefox-pw | 504.6 | 502.2 | 504.6 |

**Doğru okuma:** fetch katmanı (lightpanda) en yakın Chromium tabanlı headless
hedefe göre ~2.3× daha hızlı ve ~10× daha hafif ölçüldü. Bu, otomasyon/crawler
için doğrudan **çalıştırma maliyeti** avantajıdır.

**Kaçınılacak iddialar:** "Pergel en hızlı tarayıcı", "tüm kullanımlarda hızlı",
mutlak ms garantisi. Bunlar bu ölçümle desteklenmez. lightpanda üçüncü taraf
(AGPL) bir motordur; Pergel'in kendi motoru değildir, yalnızca fetch/otomasyon
katmanında kullanılır.

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
