# Mahoraga Öğretmen Davranış Skor Matrisi — Ölçüm Turu (2026-11-06)

Kural: yalnız alıntılı, kamuya açık doğrulanmış liderlik tablosu kanıtları skor girer [1].
Canlı ölçüm yoksa skor None kalır (plan_only) — puan uydurulmaz. Denge/bonus terimi yok;
eşik: davranış skoru / 100 >= 0.70 ise öğrenci akışı yüklenir.

## Matris (sinaps ağırlıklı)

| davranış | model | sinaps | skor (ort) | min–max | kapsam | durum |
|---|---|---|---|---|---|---|
| kod | deepseek-ai/DeepSeek-V4.1-Flash | 11 | 72.7 | 66.0–79.4 | 0.69 | yükle |
| kod | mistralai/Codestral-22B-v0.1 | 3 | — | — | 0.69 | puansız |
| kod | Qwen/Qwen3-235B-A22B | 2 | — | — | 0.69 | puansız |
| **kod (sınıf)** | — | — | **72.7** | — | 0.69 | yükle |
| arac | nvidia/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-BF16 | 3 | 17.0 | 17.0–17.0 | 0.27 | eşik altı |
| arac | NousResearch/Hermes-3-Llama-3.1-70B | 8 | — | — | 0.27 | puansız |
| **arac (sınıf)** | — | — | **17.0** | — | 0.27 | eşik altı |
| dil_karar (4 model) | — | 12 | — | — | 0.00 | plan_only |
| guvenlik (7 model) | — | 18 | — | — | 0.00 | plan_only |

Tam tablo: `/home/pc/mahoraga_davranis_skor_matrisi.md`, veri: `/home/pc/mahoraga_davranis_skor_matrisi.json`.

## Bulgular

1. **kod → yükle (eşik duyarlı).** DeepSeek-V4.1-Flash SWE-bench Verified'da 500 görevlik
   Verified alt kümesinde mini-SWE-agent ile %79.4 çözdü [2]; aynı modelin base/legacy
   konfigürasyonu %66.0 [1]. İki protokolün ortalaması 72.7, yayılım 66.0–79.4 — sınıf skoru
   eşiğin üzerinde ama alt protokol eşiğin altında, yani **protokole duyarlı**. Kaynak sayfası
   da uyarıyor: "unqualified benchmark comparisons are misleading" — her zaman effort tier
   raporlanmalı [1].
2. **arac → eşik altı.** Nemotron-3.5-Bolt-74B τ³-bench'te %17.0 [5]; davranışın kalan
   sinapslarında (Hermes-3, Noromaid, Qwen3-235B) tau kanıtı yok. Sınıf skoru 17.0, kapsam
   0.27 — Karar 2 gereği akış yüklenmez.
   Not: DeepSeek-V4.1-Flash'in tau-bench retail kanıtı güçlü (effort low/high/max =
   %80.4/%82.6/%77.0) [6] ama bu modelin 'arac' davranışında sinapsı yok; matris dışında
   notlandı, ağırlığa girmedi.
3. **dil_karar ve guvenlik → plan_only.** Bağlı benchmarklar (Netmind niyet kavrayışı,
   StegoLLM-PAQ marjinal kayıp) için kamuya açık, modellere ayrılmış doğrulanmış skor
   bulunamadı; katalog öğretmen kanıtları tasarım atfı düzeyinde. Skor yok → plan_only.
4. **Kod için bağlam dışı kanıtlar.** Codestral-22B LiveCodeBench'te %29.5 [3]; kod davranışı
   için bağlı benchmark SWE-bench Verified olduğundan bu skor matrise girmedi.
   codesota'nın SWE-bench Verified tablosundaki %79 DeepSeek-V4-Flash-Max'e ait [3] —
   V4.1-Flash ile karıştırılmamalı (çapraz-sürüm atfı yasak).

## Doğrulanamayan iddialar (matrise alınmadı)

- Qwen3-235B-A22B için aa_tau2 %23.98 (artificialanalysis, 2026-10-16; https://vectorwire.ai/models/qwen3-235b-a22b) [unverified] — sayfa metni
  JS ile üretildiğinden alıntılı kanıt dosyası oluşturulamadı. Kanıt yoksa skor yok.

## Sonuç ve sonraki adım

Şu an yalnız `kod` akışı Karar 2 eşiğini geçiyor (72.7) ve o da protokol yayılımı nedeniyle
eşik duyarlı; `arac` gerçek puanı eşiğin çok altında, `dil_karar`/`guvenlik` puanlanamaz
durumda. Pratik sonuç: öğrenci uzman montajında davranış kancası olarak yalnız kod
davranışı etkinleştirilebilir; diğer davranışlar için önce yerel ölçüm (AirLLM ile davranış
testleri, davranış kataloğu suite'leri) gerekli — kamusal kanıt bu davranışlar için yok.

sources:
[1] https://armes.ai/docs/models/deepseek/deepseek-v4.1-flash
[2] https://spec-kitty.ai/blog/benchmarking-open-weight-models-swe-bench
[3] https://codesota.com/llm/coding-benchmarks
[5] https://benchlm.ai/compare/inkling-vs-nemotron-3-5-bolt-74b-a9b-bf16
[6] https://huggingface.co/LibertAIDAI/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw/discussions/4
