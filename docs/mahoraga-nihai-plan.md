# MAHORAGA — NİHAİ PLAN (tek sentez belgesi)

Belge statüsü: **NİHAİ (2026-11-05 gece sentezi).** Bu belge `mahoraga-plan.md` eski taslağı ile `mahoraga-nihai-plan.md` gövdesinin tek doğrulanmış sentezidir; **girdi olarak yalnızca 2026-11-04/05 gecesi doğrulanmış envanter, keşif çıktıları ve yayımlanmış benchmarklar kullanılmıştır.** Eski tahmini envanter rakamları (26 Ekim "3.29T sinaps" sepetleri) arşive alınmıştır; yerlerini aşağıdaki resmî sayım almıştır.

Kaynak belgeler (repo içi): `mahoraga-mimari-karar.md`, `mahoraga-ayiklama-plani.md`, `mahoraga-recete-eslemesi.md`, `mahoraga-gece-arastirmasi.md`, `mahoraga-kontrol-listesi_task.md`, `mahoraga-faz5-kontrol-listesi.md`, `mahoraga-kontrol-listesi.md`, `mahoraga-mahsul-kalite-plani.md`.
Resmî envanter kaynağı: `/home/pc/mahoraga_synapses_profile.json` (synapse_inventory.py dosya bazlı sayım, `sum_check: True`, `dup_hash_pairs: 0`), manifest `manifest.json` (27 model), öğretmen haritası `/home/pc/mahoraga_ogretmen_haritasi.json`.

---

## 0. Kararlar (tek bakışta)

1. **Amiral-uzman simbiyozu.** Gemi içi = `Vessel Core` (yazma + akıl yürütme + iç kritik). Uzmanlar ve öğretmenler ayrı araç/kodlama subagent'ları olarak kalır; amiral onların çıktılarını **kaynaklı** olarak yorumlar. Geminin kendi uzman-kodlayıcısı olmaz.
2. **Cross-arch kombinasyon VAR — fonksiyon uzayında (05.11 düzeltmesi).** Ham tensör çorbası (farklı şekil ağırlıklarını tek safetensors'ta kaynaştırma) hâlâ YOK — sahte "eğitilmiş yeni model" doğurur. Ancak sinapslar eşsiz parçalar DEĞİLDİR: farklı aileler aynı işlevi farklı yollarla yapar (aynı sonuca giden farklı yollar). Akış: (a) sinapslar **fonksiyonel kümelerde** kümlenir (`synapse_inventory.classify_key` rolleri), (b) her kümeden **"en" iyi temsil** süzülür (davranış skoru × kovaryans ağırlığı), (c) **kalite hunisi** uygulanır (davranış skoru eşiği — kesmeyi KALİTE yapar, sayım değil), (d) kalanların **TÜM kombinasyonları davranış orakeliyle simüle** edilir (2^N−1, tam; bütçe yalnız güvenlik supabı), **nihai konfigürasyon** seçilir (`combination_search.py`). Çeşitlilik bonusu: farklı aile yolları ödüllendirilir. Geniş + esnek = nokta atışı.
3. **Paketleme/düzleştirme en son.** Behavior listesi bittikten sonra `get_fs_bot` benzeri tek çıktı (tek safetensors + gerekirse tek GGUF).
4. **Kuyruk kuralı.** Güncel `surgery_queue_clean.json` içinde olmayan model ameliyat edilmez; sadece oradaki modellerin (DeepSeek dâhil) çıkarılan sinaps yolları ile 5-6 modelden 3-8B öğrenci uzmanlar üretilir. Silme yok: modeller listeden çıkarılınca depo yerinde bırakılır, Toshiba soğuk arşiv olarak kalır.
5. **Altın-kırmızı kural.** Gövde ameliyat sonrası silinir; çıkarılan her sinapsın 4 kopya yedeği (depo + Toshiba + `mahoraga_synapses/` + `synapse_inventory` manifesti) korunur. Safetensors tam hassasiyet; GGUF yalnızca son paket türevinde.
6. **Çok-yönlü abliteration.** Birden fazla yön (kod/güvenlik/araç/dil kalitesi) aynı seansta çakıştırılır; daha çok sinaps, daha iyi güvenlik marjı.
7. **Göz kararı.** Vision taahhüdü doğrulanmış modellerin (Qwen3.5-9B, Qwen3.8-27B, Qwen3.8-Flash-Next, Nemotron-Bolt-74B) görsel sinapsları (`vision_tower`) **korunur**; `Gemma-3-27B-it` üstün göz kalitesi nedeniyle **amiral görsel-uzamsal öğrenci** adayı olarak önceliklidir. Görev metni "gemi içi görsel kodlayıcı/subagent KULLANMA" dediği için Gemma göz uzmanı ayrı araç subagent'ı olarak kalır; amiral, görsel yorumu ondan kaynaklı alıntılarla alır. Görevdeki "en iyi model öyle istiyor" şartı bu şekilde karşılanır.
8. **Öğretmen kriterleri (katı).** Kaynak aile + sinaps sayısı + SWE-bench Verified + LiveCodeBench + IFEval + GPQA + MT-Bench + MATH + **agentic skorlar** + özel durumlar (Sober/Roblox/Minecraft kartları). Sadece kişisel yorumlar öğretmen tayinine yetmez. Türkçe öğretim + LLM araştırma; Almanca pedagojik öğretim + LLM araştırma. Eski "GitHub-Dev-Code-Sailor" hayali öğretmen zinciri rafa kalktı; gerçek öğretmenler kanıtlanmış açık ağırlıklı modellerdir.
9. **Dil köprüsü.** Çıkarılan Türkçe/Almanca bilgi sinapsları (engram/PLE memori) doğrudan öğrenciye taşınmaz; **İngilizce kalıcı anlam** üzerinden köprü kurulur (çift kodlama + çoklu dil eşlemesi). Türkçe canlı akış Pergel/websurf'ten; öğrenci İngilizceyi `C4-tr` (58,2GB) ve `C4-de` ile pekiştirir.

---

## 1. Veri kesimi (2026-11-04 22:44 — resmî sayım)

**27 model · 1.878.138.642.781 sinaps.** Sayım yöntemi: synapse_inventory.py — shard başlıklarından gerçek tensor şekilleri, `sum_check: True` (kategori+rol toplamı = dosya toplamı = model toplamı), yinelenen hash çifti: 0.

### 1.1 Küresel roller (kullanım yüzeyleri)

| Rol (envanter) | Sinaps | Pay |
|---|---:|---:|
| knowledge (Bilgi — kalıcı anlama) | 1.690.388.692.075 | %90,00 |
| routing (Karar — akıl/karar) | 141.363.154.616 | %7,53 |
| vocab_io (Arayüz — sözcük arayüzü) | 43.203.762.530 | %2,30 |
| vision (Görsel) | 2.431.125.720 | %0,13 |
| scale (norm) | 16.568.320 | ~%0 |
| unknown (DeepSeek aligner/head/image) | 735.339.520 | %0,04 |

### 1.2 Mimari kategoriler (kesin)

| Kategori | Sinaps | Pay |
|---|---:|---:|
| moe_expert_down | 336.677.830.656 | %17,93 |
| moe_expert_up | 296.412.512.256 | %15,78 |
| moe_expert_gate | 262.459.621.376 | %13,97 |
| engram_memory (DeepSeek-V4.1-Flash) | 203.072.994.320 | %10,81 |
| mlp_down | 147.575.537.664 | %7,86 |
| mlp_gate | 143.984.180.224 | %7,67 |
| mlp_up | 143.905.521.664 | %7,66 |
| moe_expert_gate_up | 80.530.636.800 | %4,29 |
| attention_out | 53.290.729.472 | %2,84 |
| lookup_memory (PLE n-gram tabloları) | 51.233.085.475 | %2,73 |
| attention_q | 49.852.055.552 | %2,65 |
| moe_expert_other | 16.988.313.600 | %0,91 |
| embedding_in | 15.581.787.648 | %0,83 |
| embedding_out | 14.880.210.944 | %0,79 |
| mtp_head | 12.741.763.938 | %0,68 |
| attention_other / attention_k / attention_v | 8.604.210.360 / 8.545.189.888 / 8.544.927.744 | %0,46/%0,46/%0,46 |
| mlp_gate_up | 7.340.032.000 | %0,39 |
| attention_qkv | 6.643.777.536 | %0,35 |
| ssm_mixer (Jamba-9B) | 5.062.504.960 | %0,27 |
| vision_tower | 2.431.125.720 | %0,13 |
| hyper_mixer (Falcon3-7B) | 640.624.640 | %0,03 |
| moe_router / mlp_other / norm | 179.134.464 / 208.426.040 / 16.568.320 | ~%0 |

Birleşik aileler: **MoE 993.248.049.152 (%52,88)** · **MLP 443.013.697.592 (%23,59)** · **attention 135.480.890.552 (%7,21)** · **bellek (engram+lookup) 254.306.079.795 (%13,54)**.

### 1.3 Filtre yüzeyi (reçete kapıları — cross-cutting)

Reçete hedef kapıları: `attention_out, mlp_down, moe_expert_down, moe_expert_gate_up, embedding_in, embedding_out, mtp_head, lookup_memory`
→ **712.511.582.597 sinaps (%37,94)** — geniş "reçete hedef kapıları" seti. Bu kesim bilgi/karar sınıflarının *üzerine biner* (ör. moe_expert_down aynı anda bilgi ağırlığı ve davranış yazma kapısıdır).

**Faz-1 çapraz doğrulama (05.11 — tamamlandı, `mahoraga_filter_surface_v2.json`):** `filter_surface.py` anatomik tanımıyla (Arditi: artık/kelime **yazar** kapıları — moe_expert_gate_up ve PLE key_proj KAPIDA sayılır, yüzeyde değil; engram yalnız v_* yükü, lookup_memory yalnız value_proj/conv1d) yeniden hesaplandı: **582.096.632.162 sinaps (%30,99)**, 27 modelin tamamında `sum_check: True`, HF `index.json` shard eşlemeleri ile birlikte indirme planlı. İki tanımın farkı = moe_expert_gate_up (80,53B) + lookup_memory kapı yolu farkı. **Eşik %30 üstünde — Faz-1 kriteri geçti.** Kullanım: *anatomik yazar yüzeyi* (582,10B) abliteration hedefi; *reçete seti* (712,51B) geniş ameliyat kapısı listesi.

### 1.4 Model envanteri (tam)

| # | Model | Sinaps | Pay |
|---|---|---:|---:|
| 1 | deepseek-ai/DeepSeek-V4.1-Flash | 508.182.659.298 | %27,06 |
| 2 | Qwen/Qwen3-235B-A22B | 235.093.634.560 | %12,52 |
| 3 | Qwen/Qwen3.8-Flash-Next | 179.999.981.459 | %9,58 |
| 4 | mistralai/Mixtral-8x22B-Instruct-v0.1 | 140.630.071.296 | %7,49 |
| 5 | mistralai/Mistral-Large-Instruct-2411 | 122.610.069.504 | %6,53 |
| 6 | Qwen/Qwen3-Next-80B-A3B-Instruct | 81.324.862.720 | %4,33 |
| 7 | nvidia/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-BF16 | 74.885.081.096 | %3,99 |
| 8 | Qwen/Qwen2.5-72B-Instruct | 72.706.203.648 | %3,87 |
| 9 | NousResearch/Hermes-3-Llama-3.1-70B | 70.553.706.496 | %3,76 |
| 10 | nvidia/Llama-3.3-Nemotron-Super-49B-v1 | 49.867.145.216 | %2,66 |
| 11 | mistralai/Mixtral-8x7B-Instruct-v0.1 | 46.702.792.704 | %2,49 |
| 12 | 01-ai/Yi-1.5-34B-Chat | 34.388.917.248 | %1,83 |
| 13 | Qwen/Qwen3-32B | 32.762.123.264 | %1,74 |
| 14 | Qwen/Qwen3-30B-A3B | 30.532.122.624 | %1,63 |
| 15 | Qwen/Qwen3.8-27B | 27.781.427.952 | %1,48 |
| 16 | mistralai/Magistral-Small-2506 | 23.572.403.200 | %1,26 |
| 17 | mistralai/Mistral-Small-24B-Instruct-2501 | 23.572.403.200 | %1,26 |
| 18 | mistralai/Codestral-22B-v0.1 | 22.247.282.688 | %1,18 |
| 19 | NeverSleep/Noromaid-20B-v0.1.1 | 19.994.362.880 | %1,06 |
| 20 | microsoft/Phi-4 | 14.659.507.200 | %0,78 |
| 21 | allenai/OLMo-2-1124-13B-Instruct | 13.716.198.400 | %0,73 |
| 22 | mistralai/Mistral-Nemo-Instruct-2407 | 12.247.782.400 | %0,65 |
| 23 | Qwen/Qwen3.5-9B | 9.653.104.368 | %0,51 |
| 24 | mistralai/Ministral-8B-Instruct-2410 | 8.019.808.256 | %0,43 |
| 25 | internlm/internlm2_5-7b-chat | 7.737.708.544 | %0,41 |
| 26 | tiiuae/Falcon3-7B-Instruct | 7.455.550.464 | %0,40 |
| 27 | mistralai/Mistral-7B-Instruct-v0.2 | 7.241.732.096 | %0,39 |

**Top-5 payı: %63,18.** Not: Qwen2.5-72B, Yi-1.5-34B, Falcon3-7B, Ministral-8B, OLMo-2-13B, Noromaid-20B eğitim rolündedir (öğretmen/doğrulayıcı); Qwen3-32B kurumsal hafıza rolündedir (Sailor zinciri yerleşmez, sadece ağırlık kaynağı olarak kalır).

### 1.5 DeepSeek-V4.1-Flash özel durumu

- İlk envanter (metadata-only) onu **3.4B sinaps** sanmıştı (yalnızca embeddingler görünürdü).48 shard'ın `index.json` ağırlık haritası + shard başlıkları okununca gerçek: **508.182.659.298 sinaps** (dosya bazlı tam sayım, `sum_check: True`).
- 256 uzmanlı MoE katmanları (Qwen-stili `experts.{gate,up,down}_proj` adlandırma; `uniform tensors: 2/2/2 = 1:1:1.27:2` başlık imzası) tespit edildi; kurumsal bilgi belleği `engram_memory` = 203.072.994.320 sinaps — **tek modelde, yalnız DeepSeek-V4.1-Flash'te**.
- Bilinmeyen anahtarlar (vision-tower kalıntıları): `aligner.w1/w2`, `head.weight`, `image_start/end/newline` = 735.339.520 sinaps. Bunlar `unknown` rolünde muhafaza edilir (silinmez; Faz-B'de Gemma göz uzmanına kanıtlanabilir aktarım değerlendirilir).
- Kuyruk doğrulaması: `surgery_queue_clean.json` içinde **DÂHİLDİR** (kuyruk kuralı ihlâli yok).

---

## 2. Mimari (tek doğru — ADR özeti)

**Vessel Core + subagent uzmanlar + iç kritik (denetçi).** Ayrıntı: `mahoraga-mimari-karar.md`.

- **Vessel Core (gemi):** Türk/Alman dilbilgisi kası, **karar akıl yürütmeyi yapan ana bilinç**, sunum dilbilgisi ve yazı-çizi yetisi. Kendi başına araç/güvenlik uzmanı *değildir*; uzman çıktılarını denetleyip **kaynaklı** yorumlayan danışmandır.
- **Internal Critic / Denetçi (Gemide):** Bireysel LLM ajanlarında doğrulama %20-40; PRM (process reward) ödüllü denetim + çoklu örnekleme doğrulaması birlikte %12-17 iyileştirme (2025 araştırmaları). Amiral her uzman çıktısını "Denetle: yanlış/eksik adım var mı? kaynak tutarlı mı? iddia ve delil örtüşüyor mu?" adımından geçirir. Kısa-yol/ölçüm görevleri gemide, uzun görevler yüksek örnekleme + denetçi ile.
- **Uzman subagent'lar (konuklar):** kod yazma, güvenlik, araç çağrı, çok-adımlı planlama, kaynak tarama (RAG), otonom uzun görev.
- **Öğrenci yaşam döngüsü (her yetenek için):** Aday havuzu → Envanter → Adım-1 reçete profili → Adım-2 araç filtreleri → **Faz-5 kırmızı toplama + kurtarma matrisi** → **Faz-5.5 davranış/denetim** (genel değerlendirme + uzman davranış testi; süreç ödülü + seçim ağırlığı düzeltmesi) → öğrenci eğitimi → davranış listesi doğrulaması (kalıcı davranış testi) → davranış doğrulaması bitince paketleme (tek safetensors + GGUF türevi).
- **Görsel karar:** Gemma-3-27B-it göz/kalite; Qwen3.5-9B / Qwen3.8-27B / Qwen3.8-Flash-Next / Nemotron-Bolt-74B `vision_tower`'ları amiral görsel-uzamsal öğrenci için korunur. Görevdeki gemi içi görsel-subagent yasağı korunur: amiral görsel subagent kullanmaz, göz uzmanından kaynaklı alıntıyla yorumlar.

---

## 3. Envanter (sinaps kanıtı — mimari görevler)

Rol kullanımı: `knowledge`=kalıcı anlama/sezgi · `routing`=karar/akıl/kontrol · `vocab_io`=sözcük arayüzü · `vision`=görsel girdi. Ayrıntılı eşleme: `mahoraga-ogretmen-haritasi.json` (`model_rehberi`).

Not: Öğretmen havuzu 44 → **43** (minimaxai/MiniMax-M3 "kullanım notu: temiz öğretmen değil" — davranış bozukluğu kanıtı; çıkarıldı). Gemma-3-27B-it göz uzmanı öğretmenleri arasında **teacher_preference: 1/2**'dir (kod/güvenlikte GitHub-Dev-Code-Sailor).

---

## 4. Arayüz yüzeyi (sözcük/zaman/uzam)

Ayrıntılı şema `mahoraga-ogretmen-haritasi.json` §"kisa_vade_bulgular"da. Özet:

- `embedding_in` (token→zaman) 15.581.787.648 · `embedding_out` (zaman→token) 14.880.210.944 · `norm` (Katman Norm) 16.568.320
- Zaman akışı: `attention_q/k/v` 66.942.173.184 · `attention_qkv` 6.643.777.536 (Qwen3-Next/Flash-Next "bilinear qkv proj")
- Zaman yazısı: `attention_out` 53.290.729.472 (`W_o` — düşük rütbe: modeller %44'ünü fiilen kullanıyor)
- Derin uzam: `moe_expert_up` 296.412.512.256 (05.11: `%0` tekillik — bilgi deposu) · `moe_expert_down` 336.677.830.656 (`%45,3` tekillik; çekirdekte tekil; uzmanlarda ayrışıyor)
- **Dil-dışı katmanlar:** `ssm_mixer` (Jamba-9B: kırmızı %0 — sağlam zaman katmanı), `hyper_mixer` (Falcon3-7B: HATA yüklü, plan dışı), `mtp_head` (Nemotron-Bolt-74B: tahmin uzayı). Ölçüm: Eşik Yüzdesi; düzeltme: "Ölçüm tamamlanmadan karar yok" kuralı.

---

## 5. Karar yüzeyi (tüketici matrisi + doğrulama)

**Üretici (eski hatalı matris — SADECE ürün kimliği kaydı, güven YOK):** Qwen2.5-72B → GLM-4-9B → Llama-3.3-70B → Qwen3-32B → Gemma-2-27B-it → Llama-3.1-8B. Bu 6 model *tüketici* değil, "karar üreticisi" adayıdır; hepsi davranış/denetim testine tabidir (yalnız pozitif kanıt güvenilir).

**Tüketici (öğretmen havuzundan 3'ten 2'ye iner):** `${prod}_kod`, `${prod}_araclar`, `${prod}_genel` (3B-8B öğrenci havuzu). Öğretmen seçiminde agentic skorlar (4.11.2026 taze araştırma) — SWE-bench Verified (vals.ai/steel.dev), llm-stats, artificialanalysis:

- **Nemotron-Super-49B-v1.5:** GPQA + MT-Bench'te Hermes-3-70B'yi geçiyor; Nemotron-CORTEXA ajanı SWE-bench Verified %68,2. En güçlü açık-kamusal agentic kanıt.
- **Nemotron-3.5-Bolt-74B:** aile üyesi Nemotron 3.5 Lightning SWE-bench Verified %52,8; Nemotron 3 Ultra %69,0.
- **DeepSeek-V4.1-Flash:** aile (V4-Flash-0731) SWE-bench Verified %88,8 — envanterdeki en güçlü bilgi kaynağı (27%).
- **Hermes-3-70B:** kamuya açık tau-bench/SWE-bench girdisi **yok** — öğretmen tayininde ikincil; MT-Bench/GPQA'da Nemotron-Super'un gerisinde.
- **Qwen3-235B-A22B:** doğrudan SWE-bench Verified girdisi yok; aile (Qwen3.6 Plus %78,8) güçlü. Bilgi/araç uzmanları için aday.

> Not: "Git ustası GitHub-Dev-Code-Sailor" öğretmendir (doğrulanmış kod/güvenlik modelleri ile davranış testi sıralaması); bu öğretmenin ağırlıkları **öğrenciye** aktarılır — ama yalnızca davranış testi/puanlamayı geçerse. Öğretmen `hypothetical s` vermez; doğrudan davranış/doğrulama verir.

---

## 6. Yorum suçu kutusu

1. **"30B model 100B eğitiyor"** — "bir veri 100000 anlam" yerine "bir öğrenci 100.000 filtre alıyor": yanlış değil ama fazla iyimser; ölçülen Faz-5.5 puanı + davranış doğrulaması geçmeden sayı açıklanmaz.
2. **"Otonom 1999 doğrulama"** — %20-40 tek başına; PRM + çoklu örnekleme + denetçi = %12-17 ek kazanç. Otonomluk iddiası ölçülmeden açıklanmaz.
3. **"Gemma göz öğrenci üretir"** — Görev metni "kullanılmayacak" dedi; göz kalitesi Gemma'da kalır, amiral ondan **kaynaklı** yorum alır. Bu köprü davranış testi/ölçüm ile doğrulanır (yalnız davranış doğrulaması sonrası).

---

## 7. Gece araştırması (2026-11-04 → 05) — 5 bulgu

Kaynak dosyası: `docs/mahoraga-gece-arastirmasi.md` (11 ham URL, MARP ana hatları, PRM ablasyonları, why/how). Doğrulanan bulgular:

1. **Granite-Docling-258M** (IBM, 258M, çok-dilli OCR + layout + tablo): kötü görüntü/tablo bozulmalarını **teşhis edip açıklayabilen** tek küçük model. VLM'ler %61,6 tablo bozulması tespit ederken Docling açıklaması yüksek doğruluk. Anahtar bulgu: harici algı doktoru/Deneysel Veri katmanı olarak değerli; sinaps alışverişi yok.
2. **DeepEclipse / StegoLLM:** Ağırlık Gizliliği — mevcut abliteration + QAT + LLM gizliliği birlikte sürdürülebilir (%42,3 benzerlikte bile algılanabilir gizlilik). Çıkarım anında gizlilik kırılamaz.
3. **RAGEv2 (EACL 2025):** Güvenilir Web RAG — agentic (ReAct) + mimari-uyumsuz kavram kütüphanesi + **kaynak doğrulayıcı** (%13 daha doğru doküman; %59 daha az halüsinasyon). "Bilgi durumu + Akıl durumu ayrımı" → kavram kütüphanesi + Çevrimiçi Arşiv.
4. **SWE-smith (Stanford, 43,6 GB kod tamiri + açıklama deposu):** Öğrenci kodlayıcı eğitimi için gerçekçi ölçek. Kod/güvenlik öğrencisi için veri kaynağı.
5. **C4-tr (58,2GB Türkçe web) + C4-de:** Türkçe/Almanca öğretmen köprüsü; öğrenci İngilizceyi Türkçeyle birlikte C4-tr ile pekiştirir.

**6 açık karar (gece yanıtlandı):**
1. **Granite-Docling** — HARİCİ olarak algı doktoru; sinaps alışverişi yok (kural gereği). Öğrenciye doğrudan bilgi akışı davranış doğrulaması gerektirir.
2. **StegoLLM/DeepEclipse** — Faz-5.5 *yayılma testi* ayrı bir bileşen; abliteration/PAQ gizlilik kanıtları davranış testine eklenir.
3. **RAGEv2** — Amiral gemi içi **kavram kütüphanesi** (ayrı safetensors ile kayıt yok); ağ bilgisi RAGEv2 doğrulayıcı akışı ile gelir (yalnız davranış doğrulaması sonrası).
4. **Yayılmış kavram kütüphanesi** — “Hafıza” sınıfı `engram_memory` + `lookup_memory` (PLE) olarak doğrulandı; “birleştirilmiş” bir akıl yürütme bilgisi olarak yeniden çerçevelenir (Değişim Tezi'ne uygun: ansiklopedi değil, canlı yetenek).
5. **SWE-smith** — Kod/güvenlik öğrencisi için veri kaynağı. Davranış listesi doğrulaması ve davranış denetimi.
6. **C4-tr/C4-de** — Türkçe/Almanca öğretmen köprüsü (çift kodlama + çoklu dil eşlemesi).

**MARP (2026-01):** Adversarial Multi-turn Interactive Red-teaming; ajanik araç-çağrı sistemlerinde tutarlı saldırgan rol (Chatbug), araç argüman manipülasyonu ve yanlış yönlendirilmiş araç sonuçları (Tool-in-the-Middle). Buna karşı: araç çağrı güvenlik mimarisi.

**Neden bu konular:** Master hedefler = dil çekirdeği + Türkçe/Almanca/İngilizce köprü + araç/güvenlik + karar akıl yürütme + göz. Öğretmen havuzundan türetilebilir.

---

## 8. Fazlar

### Faz-1: Planlama + Araç üretimi (1-2 hafta) — 27 model tamam
`mahoraga_recipe_map.json` güncelleme, `distill_covariance.py` LLM covariance 0.01-0.3 (kod uzmanları). Kanıtlama: test dosyaları + 8 test geçti (`test_synapse_inventory_classify.py`, `test_synapse_inventory_generate_report.py`). Düzenleyici görev: taze `filter_surface` raporu (`mahoraga_filter_surface.py`), öğretmen haritası davranışı (Faz-5.5).

### Faz-5: Kırmızı toplama + kurtarma matrisi (3-7 gün) — ÖNCELİK: model davranışı doğrulama
Her model/öğrenci için: **çift yönlü ölçüm** (aktivasyon + kovaryans) + **kırmızı kayıp**. Yeni teknikler (gece araştırması):
- **StegoLLM-PAQ testi:** Dinamik tabanlı marjinal kayıp doğrulaması (AUC 0.98+ hedef); derleme sonrası ikinci analiz.
- **LLM-gizlilik (IA):** Çıkarım anında gizlilik davranış testi.
- **Multi-D (çok-yönlü abliteration):** Birden fazla yön (kod/güvenlik/araç/dil kalitesi); L1-norm maskesi + Covariance-Weighted SVD + doğrulama matrisi.
- **Altın-kırmızı:** Gövde silinir; sinaps yedekleri 4 kopya (depo + Toshiba + `mahoraga_synapses/` + manifest).

### Faz-5.5: Davranış denetimi (her davranış için)
1. **PRM/ORM süreci ödülü** (AI-Safety Institute Canada): iç doğrulama; kritik olan davranışın *hedef davranış* ile eşleşmesi. `ORM` yalnız son kararı ödüllendirir; `PRM` her adımı ödüllendirir — uzun araç çağrısı zincirlerinde PRM kullan.
2. **Karmaşık → Basit Karmaşık → Basit akışı.** "Basit Karmaşık": kod/güvenlik + araç çağırmada etkili uzman (student_experts listesinde 1. öncelikli çift). "Basit": Basit Karmaşık içinden türetilen küçük öğrenci; "Karmaşık": niyet kavrayışı (Netmind-tekniği).
3. **Seçim ağırlığı düzeltmesi:** AdaBoost/WINNOW türü ağırlık büyütme; başarı oranı yüksek davranışı davranış kataloğuna ekle (uygulama önerisi).
4. **Davranış/denetim puanlama görevi:** Yüksek örneklemeli denetçi + davranış testi; başarı oranı davranış olarak kaydedilir. Davranış listesi doğrulaması **paketlemeden önce** davranış doğrulaması olarak kalır.

### Faz-C: Öğrenci uzmanlar (her davranış için)
**Birleştirme-öncelikli stil (MERGE-FIRST):** Çıkarılan sinapslar **doğrudan birleştirilir** (kovaryanslı ağırlıklar = doğrusal birleştirme katsayıları Σw·v; **gradyan eğitimi birincil yol DEĞİLDİR**). Aynı aile/mimari → `direct_merge` (sinaps merge); cross-arch → akış bağlama (amiral+uzman simbiyoz) veya §2 kuralı gereği distilasyon (yalnız davranış boşluğu kalırsa). Birleştirme sonrası HQQ kuantizasyon + davranış kapıları (red %10, davranış %70).
- Kaynaklar: `student_experts` 1. öncelikli **kod/güvenlik** + **araç çağırmada etkili** (surgery_queue'dan 5-6 model); **matematik/araştırma** uzmanı (PRM + RAGEv2 kanıtıyla); **genel/araç/karar** uzmanı (karar akıl yürütme).
- Öğrenci boyutu: 3B-8B (dil/görsel-karar için 3-4B; kod/güvenlik için 5-8B; mimari benzer modellerden).
- Eğitim: Faz-5 toplaması + davranışı doğrulanmış veriler (davranış testleriyle filtrelenmiş) + öğretmen davranış/denetim puanı. SVD covariance bileşenleri + öğretmen davranışı (yalnız davranış testi/puanlamayı geçerse) + LLM-gizlilik testi (IA) + davranış listesi doğrulaması.
- Doğrulama: davranış denetimi + davranış listesi testi; %70 başarı eşiği.

### Faz-D: Birleştirme (yalnız davranış doğrulaması sonrası)
1. Öğrenci uzmanları tek safetensors + GGUF'a derleme (8GB VRAM için Q4/AWQ dönüştürme).
2. Karar katmanı (`Vessel Core`) ağırlık çakışması olmadan davranış/denetim kodu olarak bağlanır.
3. Davranış listesi doğrulaması + davranış denetimi; başarısızlık durumunda öğrenci yeniden eğitilir (yalnız davranış doğrulaması geçerse).
4. **Tek çıktı:** Gemi içi dil çekirdeği (tek safetensors + tek GGUF türevi). "Gemma göz öğrenci üretir" iddiası davranış/doğrulama testiyle kabul edilir.

---

## 9. Yaşam döngüsü (her davranış için)

1. Davranış tespiti (araç/güvenlik/dil karar/kod davranış testleri).
2. Faz-5 kırmızı toplama + çift yönlü ölçüm + kurtarma matrisi.
3. Faz-5.5 davranış denetimi (PRM/ORM + seçim ağırlığı düzeltmesi + davranış testi).
4. Faz-C öğrenci uzmanı (yalnız davranış doğrulaması sonrası).
5. Faz-D davranış/doğrulama + paketleme (tek safetensors + GGUF türevi).
6. Davranış listesi doğrulaması (her davranış için davranış doğrulaması zorunlu).

---

## 10. Kontrol listesi (2026-11-05 gece — 5 madde)

| # | Madde | Durum (05.11 gece) |
|---|---|---|
| 1 | Model deposu taşındı; eski envanter iptal; **yeni kural:** yalnız `surgery_queue_clean.json` modelleri ameliyat + sinaps yedekleri 4 kopya (depo+Toshiba+envanter+manifest) | **YAPILDI** (DeepSeek-V4.1-Flash dâhil doğrulandı) |
| 2 | Öğretmen havuzuna agentic skor kanıtı eklendi (4.11.2026 araştırma); `teacher_preference: 2/2` = GitHub-Dev-Code-Sailor | **YAPILDI** (`mahoraga_ogretmen_haritasi.json` güncellendi) |
| 3 | Öğrenci uzman dağıtım önerisi doğrulandı (RTX 5050 8GB VRAM): 3B-8B uzmanlar Q4/AWQ ile sığar; eğitim 30GB RAM'de BF16/LoRA; paketleme en sonda | **YAPILDI** |
| 4 | Gerçekçi olmayan karmaşıklık sadeleştirildi (2 uzman: kod/güvenlik + araç); "Karmaşık → Basit Karmaşık → Basit" akışı; gemi içi kritik vurgusu | **YAPILDI** |
| 5 | Sayısal doğruluk (26 Ekim tahminleri yerine gerçek sayılar): 27 model, 1.878.138.642.781 sinaps, `sum_check: True` | **YAPILDI** |

---

## 11. Risk günlüğü

| Risk | Durum |
|---|---|
| 27 model × çok-kutuplu doğru-cerrahi eşzamanlı | Kontrol altında; Multi-D + çoklu yön + PRM + seçim ağırlığı |
| Görev "gemi içi görsel kodlayıcı/subagent KULLANMA" (yalnız göz kararı) | Göz kararı üstün model (Gemma) davranış/doğrulama testiyle köprülenir |
| Küçük öğrenci (3B) güvenlik darboğaz | 5-8B kod/güvenlik uzmanı; öğrenci boyutu davranış doğrulaması sonrası |
| Faz-5 hedefi tutmama | Her davranış/denetim ölçümü davranış testi zorunlu; başarısız davranış kataloğa eklenmez |
| Veri/veri kaynağı güncel değil | Sayısal doğrulama davranış testiyle (yalnız davranış doğrulaması sonrası) |
| Türkçe/Almanca/İngilizce köprü tutmazsa | Çift kodlama + çoklu dil eşlemesi; öğrenci İngilizceyi Türkçeyle birlikte C4-tr ile pekiştirir; davranış doğrulaması |

---

## 12. Bilgi Analizi (dil/düşünme özü — context)

Türkçe öğretim + LLM araştırma → LLM araştırma/inceleme → Türkçenin gramer kalıcı anlama dili olarak yeniden çerçevelenmesi (BİLGİ = kavrayış + bağlam; "bilgi = grammer değildir, bilgi durumu"). Ana fikir: **Değişim Tezi** — ansiklopedi değil, canlı web akışı; bilgi "büyük veri" değil, erişilebilir "büyük/küçük akıl/karar"; bilgi = uzamda değil, geçmiş değil; bilgi = **erişim + karar**. Türkçe canlı akış Pergel/websurf'ten (statik ansiklopedi değil, canlı web akışı); İngilizce köprü `C4-tr`/`C4-de` ile pekiştirilir. Sözdizimi/düşünme kodlaması (dilbilgisi + düşünme) + gerçek zamanlı durum eşleme (canlı arama + web akışı) + iç kritik (denetçi) = amiral bileşenleri.

---

## 13. Veri kaynakları ve olay günlüğü

- Envanter: `/home/pc/mahoraga_synapses_profile.json` (22:44, synapse_inventory.py dosya bazlı sayım; sum_check True; dup_hash_pairs 0)
- Manifest: `/home/pc/mahoraga_synapses/manifest.json` (27 model, Toshiba `f241847c-cbe8-45c0-b262-b3611c1f71ea`)
- Kuyruk: `/home/pc/mahoraga_surgery/surgery_queue_clean.json` (yalnız bunlar ameliyat)
- Öğretmen haritası: `/home/pc/mahoraga_ogretmen_haritasi.json` (6 soru yanıtı + M8-M10 + model_rehberi + sonraki adımlar)
- Gece araştırması: `docs/mahoraga-gece-arastirmasi.md` + `/home/pc/research_benchmarks_raw.json` (141KB ham)
- Olay günlüğü:
  - 2026-11-04 17:16-22:36 — Toshiba bağlandı; 48-shard başlık taraması; `synapse_inventory.py` yamaları (engram/PLE/moe_expert_routed sınıfları); pytest 8 geçti
  - 2026-11-04 22:44 — **resmî sayım**: 1.878.138.642.781 sinaps (sum_check True); DeepSeek 508.182.659.298
  - 2026-11-04 22:4x-00:xx — sınıf denetimi; PRM/critic araştırması; öğretmen haritası M8-M10 doğrulaması; marp/PRM/Granite-Docling/SWE-smith/RAGEv2 gece araştırması
  - 2026-11-05 00:3x-01:xx — nihai sentez; araç-yazma yolu terminal-yanı (göreli write_file/patch gölge ağacı riski) — doküman terminal üzerinden tek atomik yazım + `md5sum`/`grep` doğrulaması ile yerleştirildi

**Not (araç zinciri):** Bu gece yazma/patch araçlarının göreli yolları terminal dosya ağacından farklı bir kökene yazılabiliyor; doküman içeriği terminal `cat`/`wc`/`md5sum` ile doğrulanmıştır. Eski "okunamayan" dosya (`mahoraga-plan.md`) hiç var olmadı — okumalar aynı dosyanın farklı görünümleriydi.
