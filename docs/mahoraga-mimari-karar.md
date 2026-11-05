# ADR — Mahoraga'nın Mimarî Şekli (Karar)

Tarih: 2026-11-04 · Durum: KABUL (çalışma kararı)

## Bağlam

27 modelden çıkarılan 1.471.493.868.491 sinapsın anatomik envanteri elimizde
(`/home/pc/mahoraga_synapses_profile.json`):
- Bilgi katmanı (MLP + MoE uzmanları + bellek tabloları): %81,4
- Yönlendirme (attention + router): %9,3
- Kelime haznesi: %9,25 · Görsel kule: %0,14 · Normlar: minicik
- Filtre yüzeyi (artık + kelime yazarları): %39,7 parametre payı

Bilginin doğası modüler: uzmanlarda oturuyor. MoE zaten "küçük uzmanlar +
router" deseninin kanıtı. Ayrıca 27 model farklı tokenizer/mimari ailelerinde.

## Karar

**Mahoraga = simbiyotik amiral-uzman mimarisi + iskelet (vessel):**

1. **Vessel Core (iskelet):** hafif amiral gövde + orkestratör/router +
   hafıza yönetimi. Bu bir *model* değil, bir *vücut* — görev yönlendirmesi
   ve bağlamı o taşır.
2. **Uzman subagent modelleri:** iş bölümlerine (kod, matematik, araç
   kullanımı, dil, güvenlik...) özelleşmiş küçük modeller. Sistem seviyesinde
   MoE. Her uzman 27 modelin "en" bilgi katmanından beslenir (distilasyon).
3. **Varyasyonlar:** aynı iskeletin farklı bedenleri (boyut/konfigürasyon) —
   yani tek mimari ailesi, birden fazla ürün.

## Gerekçeler

- **Cross-arch ağırlık birleştirme çalışmaz:** Mistral+Qwen+DeepSeek
  tensörlerini tek gövdeye doğrudan merge etmek tokenizer/şekil farklarından
  dolayı teknik olarak kırılgandır. Aynı aile içi TIES/DARE/Model-Soups merge
  çalışır — araç kutusunda kalır, ana yol değildir.
- **Tek dev gövde:** her güncellemede tümünü yeniden derlemek gerekir;
  simbiyozda bir uzman takılır, iskelet sabit kalır → öz-evrim (Faz 4) ucuz
  ve sürekli.
- **İzole filtre temizliği:** her uzman/çıktı kendi hedef kapısında
  doğrulanır; hata izole kalır.

## "Kuantinazosyan" = düzleştirme / paketleme

Tanım kabul: pasta pişmiş, kreması pürüzlü — dışarıdan (davranıştan) aynı
pasta kalsın ama yüzey pürüzsüz ve taşınabilir olsun. Teknik karşılığı:
tam hassasiyetli ağırlıkların kayıplı ama davranış-koruyucu sıkıştırılması
(BF16 → INT8/INT4, GPTQ/AWQ vb.). Tat hafif değişebilir (kayıplı) — o yüzden
paketlemeden SONRA doğrulama testleri tekrar edilir.

**Sıralama kanunu:** ameliyat, filtre temizliği ve derleme hep TAM
hassasiyette (GOLDEN-RED) → düzleştirme/paketleme yalnız en sonda,
dağıtımdan hemen önce.

## Etkilenen fazlar

- Faz 2 (Filtre Dedektörü): hedef kapılar uzman/çıktı adayı başına
- Faz 3 (Component Merger → **Derleme/Distilasyon**): öğretmenler → öğrenci
  uzmanlar; aynı-aile ağırlık merge yardımcı araç
- Faz 4 (Self-Evolution): uzman takası / yeniden derleme döngüsü
- Faz 5 (AGI Assembly): vessel + uzmanlar simbiyozu; varyasyonlar +
  düzleştirme/paketleme burada

## Kaynak toplama kriteri

"En" kaynak = her uzmanlık alanının en iyi BİLGİ KATMANI öğretmenleri.
27 model "her biri tam gövde olacak" değil; "hangi model hangi alanda
öğretmen" envanteri. Süzme = filtre kalıntısı temiz + bilgi katmanı seçme.
