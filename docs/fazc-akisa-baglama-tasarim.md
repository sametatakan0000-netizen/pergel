# Faz-C Akış Bağlama Tasarımı — Stream Symbiosis (2026-11-06)

## 1. Problem

Cross-arch **doğrudan ağırlık birleştirme (direct merge) kapsamı sıfır**:
`docs/fazc-merge-pilot-raporu.md` — 38 benzersiz kazanan tensör ↔ öğrenci (5-8B)
eşleşmesinde `birebir = 0`; fark kategorik (şekil farkı 6-8, anahtar yok 37-39).
Örnek: kazanan `q_proj [8192,8192]` vs öğrenci `[4096,4096]`, `lm_head`
[128256,8192] vs [151936,4096]. Σw·v doğrusal birleştirme **yalnız aynı şekil ve
aynı anahtarda** anlamlıdır (plan §Faz-D, Karar 2: "ham tensör çorbası YOK").

Aynı aile/mimari içi `direct_merge` (`fazc_merge.py`, şekil-doğrulamalı) hazır;
eksik olan, farklı mimari öğretmenlerin (20B-235B) bilgisini 3B-8B öğrenciye
**şekil bağımsız** aktarma hattıdır.

## 2. Çözüm: Akış Bağlama (Stream Symbiosis)

Ham ağırlık yerine **canlı akış** birleştirilir: sinapslar SSD'de kalıcı **uzman
akışları** olarak kalır; öğrenci onlara eğitim sırasında değil, **çalışma
zamanında** bağlanır (plan §Faz-C + §0 Karar 1: amiral-uzman simbiyozu).

### 2.1 Bileşenler

| Bileşen | Rol | Donanım |
|---|---|---|
| **Amiral (Vessel Core)** | 3B-8B öğrenci çekirdek: yazma + akıl yürütme + iç kritik; her zaman RAM/VRAM'de | laptop (RTX 5050, 8GB) |
| **Uzman akışları** | Kazanan tensörler (38 mevki, 4 kopya yedekli) Toshiba SSD'de kalıcı kütüphane; istek üzerine blok akışı | Toshiba SSD (Colibri tarzı) |
| **Öğretmen danışmanı** | Dev öğretmen (20B-235B) davranış skoru üretimi; tam yükleme YOK | AirLLM katman offload / ktransformers MoE hibrit |
| **Sınıflandırıcı (router)** | Girdi → uzman seçimi (bkz §2.3) | amiral ile aynı çekirdek |

### 2.2 Çalışma zamanı akışı (lazy offload)

1. Girdi amirale gelir; **sınıflandırıcı** hangi uzman akışının gerekli olduğuna
   karar verir (fonksiyonel kümeleme: `synapse_inventory.classify_key` rolleri —
   kod/güvenlik/araç/dil).
2. İlgili uzman tensörleri **blok akışıyla** SSD'den okunur (Colibri lazy block
   paging: tam yükleme yok; 744B int4 → 25GB RAM örneği çalışma kütüphanesi
   olarak Toshiba'ya dayanır — plan §7.2).
3. MoE uzmanları için ktransformers düzeni: aktif uzman GPU'da, kalan CPU/RAM'de.
4. Uzman çıktısı amirale **kaynaklı** döner (plan §0 Karar 1: amiral uzman
   çıktılarını kaynaklı yorumlar; geminin kendi uzman-kodlayıcısı olmaz).
5. Çıktı davranış kapılarından geçer (red %10 / davranış %70).

### 2.3 Sınıflandırıcı yönlendirmeli uzman seçimi

- Girdi (veya ara adım) → fonksiyonel küme skoru → en yüksek skorlu uzman akışı.
- Seçim **kalite hunisi** ile: davranış skoru eşiği altındaki uzman hiç yüklenmez
  (plan §0 Karar 2: kesmeyi KALİTE yapar, sayım değil).
- Saf "EN" ilkesi: her mevkide işi EN iyi yapan kazanır; denge/bonus terimi yok.
- Öğretmen davranış skorları (Top-5 = %63 sinaps) laptop'ta AirLLM ile ölçülür;
  sınıflandırıcı bu skor matrisiyle beslenir.

### 2.4 Distilasyon hattı (cross-arch'ın tek meşru yolu)

Akış bağlama davranış testinde %70 kapıyı geçemezse **distilasyon** devreye girer
(plan §Faz-C: yalnız davranış boşluğu kalırsa; gradyan eğitimi birincil yol değil):

- Kaynak: SWE-smith / C4-tr (58,2GB) / C4-de (plan §kaynaklar + Karar 9 dil köprüsü).
- Öğretmen yanıtları §2.2 offload hattıyla üretilir (tam yükleme yok).
- Hızlı düzeltme: unsloth LoRA (yalnız kalan davranış boşluğuna).
- Σw·v doğrusal birleştirme **yalnız aynı şekil/anahtarda** uygulanır
  (`fazc_merge.py --merge`); cross-arch mevkilerde hiçbir ağırlık doğrudan
  taşınmaz — bilgi akış olarak, davranış olarak taşınır.

## 3. Arayüz spesifikasyonu (TDD — test önce)

Repo standardı: TDD (RED-GREEN-REFACTOR). Uygulama başlamadan önce aşağıdaki
testler yazılır; hiçbiri geçmeden implementasyon commit'i kabul edilmez.

`src/mahoraga/fazc_stream_symbiosis.py` — modül arayüzü:

```python
class StreamSymbiosis:
    def __init__(self, winners_root: str, device: str = "cuda"): ...
    def route(self, text: str) -> list[str]:
        """Sınıflandırıcı: girdi → uzman akışı adları (kalite hunisi uygulanmış)."""
    def stream_expert(self, name: str, blocks: list[int]) -> Iterator[Tensor]:
        """Colibri tarzı blok akışı: yalnız istenen bloklar SSD'den okunur."""
    def consult_teacher(self, prompt: str, teacher: str) -> TeacherScore:
        """AirLLM/ktransformers offload ile davranış skoru; tam yükleme YOK."""
    def distill_gap(self, dataset: str, gap: float) -> LoRAResult:
        """Davranış boşluğu > 0 kalırsa unsloth LoRA düzeltmesi."""
```

Test listesi (`tests/test_fazc_stream_symbiosis.py`):

1. `test_route_selects_expert_by_role` — kod girdisi kod uzmanına, güvenlik
   girdisi güvenlik uzmanına gider; denge terimi olmadan en-yüksek skor kazanır.
2. `test_route_respects_quality_funnel` — davranış skoru eşiği altındaki uzman
   hiç yüklenmez.
3. `test_stream_expert_reads_only_requested_blocks` — blok akışında SSD'den
   okunan bayt, tam tensör boyutundan düşük (lazy kanıtı).
4. `test_consult_teacher_no_full_load` — öğretmen danışmanı 8GB VRAM bütçesini
   aşmaz (AirLLM katman offload).
5. `test_sigma_wv_same_shape_only` — Σw·v yalnız aynı şekil/anahtarda uygulanır;
   cross-arch mevkide hata/direkt atlanma.
6. `test_distill_gap_triggers_only_on_gate_miss` — davranış kapısı geçilirse
   LoRA tetiklenmez; kalırsa tetiklenir.
7. `test_expert_sources_have_4_copies` — uzman akışı kaynağı 4 kopya yedek
   manifestiyle doğrulanır (altın-kırmızı: sinaps asla silinmez).

## 4. Sıralama (mevcut duruma göre)

1. Bu doküman (tasarım) → davranış test yığını (taşınabilir: AirLLM/Colibri katman
   akışı + %70 kapı) → `fazc_stream_symbiosis.py` implementasyonu (TDD).
2. Sınıflandırıcı skor matrisi: öğretmen davranış skorları (Faz-5/Faz-5.5 ölçümü).
3. Davranış boşluğu kalırsa: distilasyon (SWE-smith/C4-tr) + unsloth LoRA.

## 5. Dosyalar

- `docs/fazc-merge-pilot-raporu.md` — problem kanıtı (kapsama 0)
- `docs/mahoraga-nihai-plan.md` — §0 Karar 1-2, §7.2, §Faz-C/§Faz-D bağlamı
- `src/mahoraga/fazc_merge.py` — aynı şekil/anahtar için hazır Σw·v mekanizması
- `src/mahoraga/fazc_shard_collect.py` — 38/38 kazanan toplama (gece COLLECT tamamlandı)
