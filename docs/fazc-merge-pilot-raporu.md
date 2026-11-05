# Faz-C Birleştirme Pilotu — Kapsama Raporu (2026-11-05)

## Yöntem
`fazc_merge.py --report`: manifest 57 mevki kaydı (38 benzersiz tensör) ↔ öğrenci
`model.safetensors.index.json` + shard başlıkları (HTTP Range, sadece başlık indirildi).
Eşleşme kuralı: **anahtar adı + şekil birebir** (direct_merge). Ağırlık kuralı: w ∝ n_synapses.

## Sonuç (öğrenci adayları, 5-8B sınıfı)

| Öğrenci | birebir | şekil farkı | anahtar yok |
|---|---|---|---|
| Qwen/Qwen3-8B | **0** | 8 | 37 |
| mistralai/Mistral-7B-v0.3 | **0** | 8 | 37 |
| deepseek-ai/DeepSeek-V2-Lite-Chat | **0** | 6 | 39 |
| mistralai/Mistral-Nemo-12B-Instruct | erişilemedi (gated/401) | — | — |

Örnek uyuşmazlıklar: `model.layers.18.self_attn.q_proj` kazanan [8192,8192] vs öğrenci
[4096,4096]; `lm_head` kazanan [128256,8192] vs [151936,4096]; Noromaid `k_proj`
[5120,5120] öğrenci MHA boyutlarıyla hiç eşleşmiyor.

## Yorum (plan §Faz-C + §2 + Karar: "cross-arch merge YOK")
- Öğretmenler (20B-235B) ile 3B-8B öğrenciler arasında **doğrudan ağırlık birleştirme
  (direct_merge) kapsamı sıfır**: boyut farkı kategorik.
- Plan gereği sıra: **akış bağlama (amiral+uzman simbiyoz)** → davranış boşluğu kalırsa
  **distilasyon**. Gradyan eğitimi birincil yol değil.
- `fazc_merge.py` mekanizması hazır ve şekil-doğrulamalı: aynı mimarili küçük bir öğrenci
  (ör. DeepSeek-V4-Flash-3B gelirse) doğrudan birleştimeye hazırdır; `--merge` modu
  Σw·v + α-karışımı uygular, çıktı 4 kopya manifest yedeğiyle Toshiba'ya yazılır.

## Sıradaki iş
1. **Akış bağlama tasarımı:** kazanan tensörler SSD'de kalıcı uzman akışları olarak
   bağlanır (Colibri lazy-block benzeri); öğrenci çekirdek (amiral) + sinaps akışları.
2. **Davranış test yığını** (taşınabilir): AirLLM/Colibri katman akışı + %70 kapı.
3. Davranış boşluğu kalırsa: SWE-smith/C4-tr ile distilasyon verisi (plan §kaynaklar).

## Dosyalar
- `merge_report_Qwen__Qwen3-8B.json`, `merge_report_mistralai__Mistral-7B-v0.3.json`,
  `merge_report_deepseek-ai__DeepSeek-V2-Lite-Chat.json` (kapsama verisi)
- `src/mahoraga/fazc_merge.py` (birleştirme mekanizması, d5136fd sonrası)
