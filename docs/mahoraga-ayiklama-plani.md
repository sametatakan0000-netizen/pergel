# Mahoraga — Sinaps Ayıklama Planı (AGI Girdi Defteri)

**Tarih:** 2026-11-04 · **Durum:** kesinleşmiş iş bölümü
**Girdi:** `/home/pc/mahoraga_synapses_profile.json` (27 model, 1.471.493.868.491 sinaps, 0 unknown)
**Çıktı:** `/home/pc/mahoraga_ayiklama_plani.json` (sınıf defteri, model bazlı)

## İş Bölümü — Net Çizgi

| İş | Kim | Not |
|---|---|---|
| Red/refusal ayıklama (abliteration) | **Heretic & benzeri araçlar** | Gövde üzerinde koşarken yapılır; asla yeniden türetmeyiz |
| Filtreler **nerede** oturuyor (harita) | **Biz** | `mahoraga_recipe_map.json` + `mahoraga_filter_surface.json` |
| Sinaps sınıflandırma + işaretleme | **Biz** | Bu defter |
| Besleme planı (hangi sinaps → hangi uzman) | **Biz** | Sıradaki adım |
| Derleme (Vessel + uzmanlar) | **Biz** | ADR'ye göre (`docs/mahoraga-mimari-karar.md`) |
| Paketleme / düzleştirme (kuantizasyon) | **En sonda** | Ameliyatlar BF16 bittikten sonra |

## Sınıf Defteri (roller toplamı, `sum_check=True`)

| Sınıf | Sinaps | Pay | AGI'deki yeri |
|---|---:|---:|---|
| **BILGI** (knowledge) | 1.197.180.052.515 | %81,36 | **Kabiliyet** (dil/mantık/uzmanlık) — arşiv DEĞİL; distilasyonla taşınır |
| **KARAR** (routing) | 136.212.015.232 | %9,26 | Vessel router tasarımı referansı |
| **ARAYUZ** (vocab_io + scale) | 136.082.517.584 | %9,25 | Vessel tokenizer / çıkış / normalizasyon |
| **GORSEL** (vision) | 2.019.283.160 | %0,14 | Görsel uzman beslemesi |

## Filtre Yüzeyi Etiketi (cross-cutting — sınıf DEĞİL, işaret)

Bu yüzeyler BILGI/KARAR/ARAYUZ'un **içinden geçer**; amaç onları ayırmak değil,
**gövde hedefli shard'larla geri çekildiğinde araçla temizlenecek/izlenecek yeri bilmektir.**

- Reçete kategorileri: `attention_out`, `mlp_down`, `moe_expert_down/gate_up`,
  `embedding_in`, `embedding_out`, `mtp_head`, `lookup_memory`
- Bu defterdeki sayım: **714.305.432.691 (%48,54)** — MoE gate_up + lookup tamamı dahil
- `mahoraga_filter_surface.json` sayımı: **583.890.482.256 (%39,68)** — yalnızca
  `residual_writer` kesişimi + `embedding_in/out` + `mtp_head` + `lookup_memory:value_proj`
- **Farkın sebebi reçete granülaritesidir** (gate_up ve lookup'un tamamı sayılıp sayılmaması);
  iki rakam da doğrudur, kendi tarifleriyle anılır. Kesin yüzey için filter_surface raporu esastır.

## Değişim Tezi (çekirdek ilke)

- *"Değişmeyen tek şey değişimin kendisi."* Web'deki olgular sürekli değişir
  → **taze bilgi websurf'ten** (Pergel query fan-out + citation grounding).
- **BILGI = kabiliyet, ansiklopedi değil.** Olgular bayatlar; düşünme biçimi
  (dil, mantık, uzmanlık kalıpları) bayatlamaz. Websurf bile bu makine olmadan
  çalışmaz: getirilen sayfayı okuyup sentezleyecek kısım ağırlıklardadır.
- **Vessel router politikası:** volatil sorgu → web; kalıcı soru → ağırlık.
  Ağırlıkta kalan bayat olgular doğrulama zincirinde ezilir.
- **Besleme = kabiliyet distilasyonu** (ansiklopedi kopyalama DEĞİL).

## Boru Hattı (sıra)

1. **Sınıflandırma** → bu defter (bitti)
2. **Besleme listeleri** → her uzmana hangi modelin **kabiliyeti** öğretmen (ADR: "en" bilgi katmanı öğretmenleri) — SIRADAKİ
3. **Gövde geri çekme** → yalnız hedef shard (`mahoraga_filter_surface.json` alışveriş listesi)
4. **Araçla temizleme** → Heretic benzeri araç gövde üzerinde; biz sadece işaretleriz
5. **Derleme** → ADR: Vessel Core + uzman simbiyozu (distilasyon/orkestrasyon)
6. **Paketleme/düzleştirme** → en sonda (BF16 → INT8/INT4)

## Kural Hatırlatması

- Red yönü **bulmayız** — araçların çıktısını okuruz.
- Gövde geçicidir; sinapslar asla silinmez (ALTIN-KIRMIZI).
- Cross-arch ağırlık merge YOK — bilgi akışı distilasyonla.
