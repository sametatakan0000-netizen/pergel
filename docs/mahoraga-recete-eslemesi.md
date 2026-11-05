# Adım 2 — Kamuya Açık Abliteration Reçetelerinin Anatomimize Eşlemesi

Tarih: 2026-11-04 · Makine-okunur: `/home/pc/mahoraga_recipe_map.json`
Kaynaklar birebir doğrulandı (nanofatdog README, junafinity/orcarouter kartları).

## Ortak Desen (tüm reçeteler)

Red davranışının taşıyıcısı **artık akışa yazan matrislerdir**:
`embed_tokens` (girdi yazısı) + her katmanda `o_proj` + `down_proj` (MoE'de
`expert_down`). PLE/hibrit modellerde buna **bellek yük yolu** (`ple.value_proj`)
ve `mtp_head` eklenir. Yöntem ailesi: harmful/harmless aktivasyon farkından
"red yönü" çıkar, yazan matrislerden **ortogonal projeksiyon / row-space
edit** ile çıkar. (Arditi 2406.11717 = kanonik; rank-1 edit = modern uygulama.)

**Önemli:** PLE'nin **gate yolu** (key_proj/norm_key/norm_query) ve
`conv1d/norm_conv` reçetelerde **dokunulmaz** — bellek *seçimi* korunur,
red taşıyan *yazı* temizlenir. Bizim `lookup_memory` ayrımımız birebir tutuyor.

## Aile → Hedef Kapılar (özet)

- **Llama-3** (Hermes-3-70B, Nemotron-74B): embedding_in + attention_out + mlp_down — Arditi, confirmed
- **Qwen2.5-72B**: attention_out + mlp_down + embedding_in — sci4ai kartı formülü, confirmed
- **Qwen3 dense/MoE** (32B, 235B, 30B, 122B): + moe_expert_down — nanofatdog, confirmed
- **Qwen3 hibrit+PLE** (Next-80B, 3.5-9B, 3.8-27B/Flash-Next): + mtp_head + lookup_memory:ple.value_proj — nanofatdog + orcarouter, confirmed
- **Mistral ailesi** (7B, Small, Nemo, Large, Ministral, Codestral, Magistral, Noromaid): standart üçlü — 4 araç benchmark'ında stabil, confirmed
- **Mixtral MoE**: standart + expert_down — inferred (Mixtral-özel reçete yok)
- **Yi-1.5-34B**: standart üçlü AMA araç seçimi kritik: Heretic'te kırılgan
  (-26.5% GSM8K), DECCP/ErisForge'da stabil — confirmed
- **Falcon3-7B**: standart üçlü, Heretic SSM-kapsamlı — confirmed
- **Phi-4, OLMo-2, internlm2.5**: standart üçlü — inferred
- **DeepSeek-V4.1 (Engram)**: **kamuaya açık reçete YOK** — anatomik benzerlikle
  payload yolu infer; Adım 4'te deneysel doğrulanacak (boşluk olarak işaretli)

## Araç Kararı (pipeline için)

1. **Birincil:** `nanofatdog/LLM-abliterate` (Apache-2.0) — dense/hibrit/MoE/VLM
   otomatik tespit; extract(Cohen's d/AUC)→sweep(lambda)→apply(rank-1)→verify
   (vision/lm_head dokunulmaz + davranış testleri). TDD akışımızla birebir.
2. **Arama:** `p-e-w/heretic` — Bayesian TPE, 16/16 kapsama (Yi'de dikkat).
3. **Toplu/shard'lı:** `NousResearch/llm-abliteration` (DECCP).
4. **Sınır:** FailSpy/abliterator yalnız 5/16 (TransformerLens bağımlılığı).

**Teslimat biçimi:** rank-1 **LoRA adapter** (Abliterix) — temel ağırlıklar
bozulmaz → GOLDEN-RED'e birebir uyumlu; filtre geri alınabilir, lambda
ayarlanabilir, katman bazlı dozlanabilir.

## Sıradaki (Adım 4 — pilot)

Tek modelde ucuz doğrulama: **Ministral-8B** (15 GB, %52 model kapasitesi,
Mistral = en stabil aile, hedef 2 shard). Alternatif: Mistral-7B.
Başarı ölçütü: red oranı ↓, kabiliyet kaybı ≤1pp, KL drift küçük; verify
kapısı = vision/lm_head hash değişmez + davranış testleri.
