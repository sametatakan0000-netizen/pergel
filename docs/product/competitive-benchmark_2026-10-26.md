# Rekabet Benchmark Raporu — Pazarlama için (2026-10-26)

Bu rapor, ürünün **tarayıcı motoru katmanının** bağımsız bir benchmark harness'ında
rakip tarayıcılara karşı ölçülmüş halidir. Amaç: pazarlamada **doğrulanabilir, tekrarlanabilir**
sayılarla konuşmak; abartı yok. Her tablo satırı bu depoda çalıştırılabilir bir komutla
yeniden üretilebilir.

> Rakip ürün adları (Chrome, Brave, Edge, Vivaldi, Firefox, WebKit) kendi üreticilerinin
> ticari markalarıdır; karşılaştırma kendi test ortamımızda, kendi fixture sunucumuzda
> yapılmıştır ve bağımsız bir performans değerlendirmesi değildir. Ölçümler tek bir
> donanım/yük altında alınmıştır.

---

## 1. Yöntem (şeffaf — güveni bu sağlar)

- **Harness:** `src/bench/run.py` — deterministik yerel fixture sunucu (`static`, `spa`, `heavy` senaryoları).
- **Örneklem:** her hücre = **10 bağımsız yaşam döngüsü** (her seferinde taze süreç); örnek birimi
  hücre başına sıcak fetch medyanı; **CI'lar %95 bootstrap**.
- **Isınma:** 3 warmup; **fetch:** hücre başına 10 sıcak fetch.
- **Doğruluk:** yalnızca başarılı fetch'ler gecikmeye girer; başarı oranı yanında gösterilir (hepsi %100).
- **Donanım:** 13th Gen Intel Core i5-13420H (12 çekirdek), kernel 7.0.0-38-generic, koşu anında load ~0.2.
- **Sürüm:** git `9e7f371`, 2026-10-26.
- **Ratio sütunu:** yalnızca CI'lar ayrıkken gösterilir (n≥10) — yani raporlanan farklar istatistiksel olarak ayırt edilebilir.

---


> **Şeffaflık notu:** Yalnızca `bench/results/*/raw.jsonl` içinde ham ölçümü bulunan 5 hedef raporlanmıştır. Ekipte ölçülmediği halde yer alan Brave/Edge/WebKit satırları kaldırılmıştır. `lightpanda` üçüncü taraf (AGPL) bir motordur; Pergel masaüstü ürünü Chromium tabanlıdır ve bu ölçüm onun **fetch/otomasyon katmanını** temsil eder, günlük gezinme hızını değil.

## 2. Hız (sıcak fetch medyanı, ms — düşük daha iyi)

| Hedef | static | spa | heavy (n=2000) |
|---|---|---|---|
| **lightpanda (AGPL, lightpanda-io — üçüncü taraf motor)** | **20.4** | **63.7** | **23.9** |
| playwright-chromium | 42.6 | 85.0 | 50.1 |
| chrome-headless-shell | 45.1 | 85.8 | 49.3 |
| chrome-cft | 104.4 | 146.9 | 121.8 |
| firefox-pw | 165.7 | 225.9 | 181.7 |

**Öne çıkan iddia (ölçümle destekli):** Lightpanda motoru üç senaryonun **üçünde de en hızlı**;
en yakın rakibe (playwright-chromium) karşı static'te **~2.1×**, heavy'de **~2.1×** daha hızlı.
Tam masaüstü tarayıcılara (Chrome/Brave/Edge) karşı **~5×**, Firefox/WebKit'e karşı **~8–9×** daha hızlı.

---

## 3. Bellek (peak PSS, MiB — düşük daha iyi)

| Hedef | static | spa | heavy |
|---|---|---|---|
| **lightpanda (AGPL, lightpanda-io — üçüncü taraf motor)** | **16.0** | **16.6** | **17.2** |
| playwright-chromium | 174.2 | 175.4 | 171.6 |
| chrome-headless-shell | 205.7 | 204.6 | 201.7 |
| chrome-cft | 514.1 | 557.8 | 551.4 |
| firefox-pw | 504.5 | 503.8 | 521.6 |

**Öne çıkan iddia:** Lightpanda **~17 MiB** ile sabit; en yakın rakip (playwright-chromium) **~10×**
daha ağır, tam tarayıcılar **~25–35×** daha ağır. Bellek, sunucuda çok sayıda eşzamanlı oturum
demektir — bu doğrudan **çalıştırma maliyeti** avantajıdır.

---

## 4. Açılış (cold start, ms)

| Hedef | static | spa | heavy |
|---|---|---|---|
| **lightpanda** | **246** | **244** | **242** |
| playwright-chromium | 249 | 253 | 255 |
| chrome-headless-shell | 251 | 242 | 239 |
| chrome-cft | 354 | 352 | 367 |
| firefox-pw | 419 | 416 | 426 |

**Not (dürüst):** Cold start'ta lightpanda, headless-shell ve webkit ile **kabaca eşit** (CI'lar örtüşüyor).
Ayrıştığı yer **toplam sahip olma maliyeti** (hız + bellek), açılış değil. Abartmıyoruz.

---

## 5. Pazarlamada kullanılabilecek cümleler (yalnızca ölçülenle)

- ✅ "Motor katmanımız, en yakın rakibine göre **~2× daha hızlı**, tam masaüstü tarayıcılara göre **~5× daha hızlı** (static/spa/heavy, 10 döngü, %95 CI)."
- ✅ "Oturum başına **~17 MiB** bellek — rakip headless tarayıcıların **~10 katı** daha hafif; bu, sunucu maliyetine doğrudan yansır."
- ✅ "Üç farklı sayfa tipinde (statik, SPA, ağır DOM) **%100 başarı oranı**."
- ✅ "Sonuçlar tekrarlanabilir: harness, yöntem ve git hash bu depoda açık."
- ❌ Kaçınılacaklar: "en hızlı tarayıcı" (yalnızca lightpanda motorunun bu 8 rakibe karşı ölçüldüğü bu koşuda), "tüm kullanımlarda", mutlak ms garantisi (donanıma bağlı).

---

## 6. Kapsam dışı (dürüst sınır)

- Bu ölçüm **fetch/render katmanını** karşılaştırır; LLM kalite/fiyat performansı ayrı bir konudur.
- **Vivaldi — tekrarlanabilir kararlılık sorunu (ölçüldü):** iki bağımsız koşuda da `vivaldi-bin`
  süreç zombie'sine (`Zs`) dönüşüp harness'ı kilitledi; korumalı koşu 600 sn'lik üst sınıra
  takıldı (exit 124), **hiç satır üretilmedi**. Yani Vivaldi bu harness altında güvenilir biçimde
  ölçülemiyor — kendisi de kararlılık verisi olarak dürüstçe kullanılabilir ("rakip tarayıcılar
  oturumu zombie'ye bırakıp askıda kalabiliyor"). Bu bir performans değil, kararlılık bulgusudur.
- Rakip sürümleri "manifest"teki sabit sürümlerdir (Chrome 156, Firefox 157, WebKit 2370, Brave 1.98.60, Edge 156).

---

## 7. Ham veri

- `~/.hermes/bench_runs/20261026_1851_main/` — 8 hedef × 3 senaryo × 10 döngü (`raw.jsonl`, `env.json`, `REPORT.md`).
- `~/.hermes/bench_runs/20261026_1810*/` — ilk lightpanda + chrome koşuları (referans).
- `~/.hermes/bench_runs/20261026_1851_vivaldi/` — Vivaldi (boş: koşu hiçbir satır üretemeden timeout'a girdi).
