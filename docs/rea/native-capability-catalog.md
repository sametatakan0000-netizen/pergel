# Mağaza İçerik Analizi → Native Yetenek Kataloğu (2026-10-25)

> Soru (HFY): "Mağazaların analizde içeriklerini fulledik mi? Yararlı olabilecek
> her şeyi native koymak iyi olur." Cevap: **altyapı** analizi tam (`extension-stores.md`
> — MV3 kotaları, imzalama, ret sebepleri), **içerik/kategori** analizi eksikti. Bu
> döküman onu kapatır: hangi eklenti kategorisi popüler, hangisi bizim motor
> katmanlarımızla native yapılabilir, hangisi ürün kapsamı dışı. Kaynaklar web
> araştırması (StoreTally, HexDigest, AboutChromebooks, 2026-10). Tümü salt-okunur.

## 1. Kategori pazarı (2026-10, gerçek sayılar)

- CWS toplam ~251.488 eklenti; **Productivity %55,5** (~62.127), Lifestyle %33,3,
  Developer Tools %8,5, Games %2,7. Medyan kurulum **17**, ortalama 12.304
  (uçlar çekiyor); yalnızca **337 eklenti 1M+** kullanıcıda. Ocak 2026'da **300
  kötü amaçlı eklenti / 37M indirme** raporlandı → native/yerleşik avantaj: güvenlik.
- En çok kurulu (StoreTally): Adobe Acrobat 332M, AdBlock 62-65M, Grammarly 36-41M,
  uBlock Origin 11-14M, Dark Reader 7M, Adblock Plus 40M. **Top-10 Productivity
  tüm kullanıcıların %42'sini** tutuyor.
- MV3 kırılması: tam uBlock Origin Chrome'da öldü (Tem 2025) → **uBlock Origin Lite
  17M**. Engelleme/gizlilik kategorisi "kısıtlı MV3" ile boğuşuyor — bizim **MV3
  kotu-dışı kural motorumuz** (92k+ kural, kota yok) tam burada farklılaştırıcı.

## 2. Native'e-değer sınıflandırma (motor katmanımızla eşleştirme)

İşaretler: ✅ = uygulandı (bu sprint), 🟢 = mevcut katmanlarla native yapılabilir,
🟡 = kısmi/ek iş, 🔴 = ürün kapsamı dışı (etkileşimli tarayıcı/sync/gizli anahtar gerekir).

| # | Kategori | Örnek (kullanıcı) | Native? | Bizim karşılığı |
|---|---|---|---|---|
| 1 | Reklam/izleyici engelleme | AdBlock 65M, uBO 14M | ✅ | `rule_engine`+`abp_compiler`+`cdp_adblock_driver` (4 katman, default-on) |
| 2 | Cookie-bildirim/annoyance gizleme | "cookie pop-up blocking" | 🟢 | cosmetic + procedural katmanı — annoyance listesi ekle (EasyList Cookie / Fanboy Annoyances) |
| 3 | Reader Mode / okuma | Native reader | 🟢 | `html_to_clean_markdown` **zaten** reader-çıkarımı; "reader" endpoint'i = sarmalayıcı |
| 4 | Dark mode | Dark Reader 7-10M | 🟢 | `build_injection` şablonuna CSS transform ekle (Dark Reader'ın renk-yeniden-değerlendirme mantığı) |
| 5 | Odak/dikkat engelleme | Freedom, Cold Turkey | 🟢 | ağ DNR kuralı = site bloğu; ürün "focus policy" listesi |
| 6 | Görev/not yakalama | Todoist, Web Clipper | 🟢 | clean-markdown + `record_page` (zaten DB'ye sayfa kaydediyor) |
| 7 | Ekran görüntüsü | — | 🟢 | CDP `Page.captureScreenshot` (driver'da zaten CDP var) |
| 8 | Endpoint/iz envanteri | (geliştirici) | ✅ | `discover_network_endpoints` + HAR analizi (REA'da zaten) |
| 9 | Çeviri | DeepL, Google Translate | 🟡 | metin çıkarımı hazır; çeviri = router'da bir LLM çağrısı (ucuz) — native "post-process" |
| 10 | Metin büyütme/erişilebilirlik | — | 🟡 | CSS injection ile kısmi; tam erişilebilirlik kapsam dışı |
| 11 | Şifre yöneticisi | Bitwarden 3M, 1Password | 🔴 | gizli anahtar kasası + sync = ürün kapsamı dışı (ve hedef: native eklenti ile 3. taraf çalışsın) |
| 12 | Yazım asistanı | Grammarly 36-41M | 🔴 | her tuşta bulut LLM + tarayıcı-içi overlay; bizim çekirdek (fetch/extract) değil |
| 13 | Sekme yönetimi | OneTab, Workona | 🔴 | etkileşimli canlı tarayıcı gerekir; biz fetch-çekirdek motoruz |
| 14 | PDF düzenleme/imza | Adobe Acrobat 332M | 🔴 | ayrı ürün; REA'da incelendi |
| 15 | VPN/proxy, indirme yöneticisi | Xunlei 68M | 🔴 | ağ altyapısı / lisanslı indirme — kapsam dışı, REA kırmızı çizgi |

## 3. Çıkarım: neyi native koymalı?

1. **Yapıldı (bu sprint):** kategori #1 (reklam/izleyici/gizlilik) — 4 katman motor,
   gerçek EasyList+uAssets, default-on. Bu en büyük kategori ve en güçlü farklılaştırıcı
   (MV3 kotu-dışı 92k+ kural).
2. **Düşük efor / yüksek değer (🟢):** #2 annoyance-cookie, #3 reader endpoint'i,
   #4 dark mode, #5 focus bloğu, #6 not-kaydetme, #7 ekran görüntüsü — hepsi **mevcut
   motor katmanlarının** (cosmetic/DNR/injection/clean-markdown/CDP) üzerine ince
   bir sarmalayıcı. Yeni motor gerekmez.
3. **Kapsam-dışı (🔴):** #11-15 — bunlar "native eklenti desteği"nin **sebebi**:
   3. taraf eklentiler (Bitwarden, Grammarly) bizim platformda çalışmalı. Yani biz
   onları native yazmayız, MV3 yüzeyini sağlarız ki onlar çalışsın.
4. **Ürün özeti:** "mağazadaki her şeyi native koymak" doğru hedef değil — mantıklı
   hedef: **motor-katmanıyla çözülebilen her şeyi native (🟢'ler), platform-gerektiren
   her şeyi eklenti-yüzeyiyle destekle (🔴'lar)**. Kategori #1'i yaparak bu ayrımın
   en değerli ucunu tamamladık.

## 4. Sonraki adaylar (sıralı, hepsi ince sarmalayıcı)

1. Cookie/annoyance gizleme (Fanboy Annoyances listesi → mevcut cosmetic katmanı).
2. Reader-mode endpoint (clean-markdown zaten var).
3. Dark-mode CSS transform (build_injection'a ekle).
4. Focus-policy site bloğu (DNR kuralı).
5. Ekran görüntüsü (CDP captureScreenshot).
Hepsi TDD ile; ayrı liste/transform olarak test edilir. İstendiğinde tek tek açılır.
