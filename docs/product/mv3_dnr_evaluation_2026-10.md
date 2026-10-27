# MV3 / DNR Yüzey Değerlendirmesi — Brave, Edge, Vivaldi, Opera, Chrome-CFT (Ekim 2026)

Bu bölüm yalnızca **ölçülebilir / belgelenmiş** durumları raporlar (kural limiti sayıları, resmi
zaman çizelgeleri, resmi vendor duyuruları). Her iddianın yanında kaynak URL vardır. Bu deponun
`mv3_surface.py` (MV3 manifest ayrıştırma + DNR kural derleme) ve `extension_host.py` (izole
ExtensionHost) yüzeyine karşılık gelen test bağları son bölümde verilmiştir. Burada kod yoktur,
yalnızca değerlendirme vardır.

---

## 1. Vendor başına tek satır başlık

- **Brave** — MV3 olgunluğu: **tam (Chromium MV3 sözleşmesi)**, ayrıca 4 seçili MV2 uzantısı vendor
  backend'inde sunulur; DNR kısıtı "standart Chromium limitleri + non-guarantee düşük-tutarlı
  değişken ölçüm" notu (resmi DNR limit dokümanı Brave'e özel sayı vermez).
- **Microsoft Edge** — MV3 olgunluğu: **tam**, MV2 tüketici geçişi Ağu 2026'da başladı (tümüyle
  2026 sonu hedefi, kurumsal 2027 başı); DNR kısıtı: resmi limitler Chromium'la aynı (Edge kendi
  DNR kotası dokümanı yayımlamaz).
- **Vivaldi** — MV3 olgunluğu: **tam**, MV2 "Chromium'da kaldığı sürece" destekli (resmi hedef
  Haz 2025); DNR kısıtı: Chromium sözleşmesi geçerli, ayrıca yerleşik içerik engelleyici bu
  kısıtların dışındadır.
- **Opera** — MV3 olgunluğu: **tam**, MV2 şu an korunuyor (Haz 2026 resmi beyanı) ve store MV3'e
  dönüşüyor; DNR kısıtı: Chromium limitleri + yerleşik reklam engelleyici bu limitlerden muaf.
- **Chrome for Testing (Chrome-CFT)** — MV3 olgunluğu: **Chrome ile eşit API** (vanilya MV3+DNR),
  ama "test build" doğası gereği markalı Chrome'un aksine `--load-extension` açık kalır; DNR
  kısıtı: Chrome DNR limit dokümanı birebir geçerli (deneysel varyant raporlanmaz).

---

## 2. Karşılaştırma tablosu

| Vendor | MV3 lifecycle (service worker, host_permissions, content_scripts) | DNR kural limitleri (regexFilter, dynamic, .updateDynamicRules) | Popüler MV3 uzantı uyumluluğu (uBO / uBO Lite / AdBlock Plus) | Vendor'a özgü kısıt |
|---|---|---|---|---|
| **Brave** | Standart MV3 (Chromium ile aynı). DNR motoru Chromium'un kendi motorudur; Brave yalnızca patch katmanıyla entegre olur ([brave.com/blog/brave-shields-manifest-v3](https://brave.com/blog/brave-shields-manifest-v3/)). | Resmi Brave-spesifik DNR kotası dokümanı yok; Chromium DNR limit dokümanı (dyn 30k / safe 30k, non-safe 5k, regex 1000) referans alınır ([developer.chrome.com/.../declarativeNetRequest](https://developer.chrome.com/docs/extensions/reference/api/declarativeNetRequest)). | **Tam uBO (MV2) çalışır** — vendor backend'inde barındırılan 4 uzantıdan biri: uBO, AdGuard, NoScript, uMatrix, `brave://settings/extensions/v2` üzerinden ([brave.com/blog/brave-shields-manifest-v3](https://brave.com/blog/brave-shields-manifest-v3/)). uBO Lite (MV3) ayrıca mağazadan kurulabilir durumda ([ublockorigin.com/lite](https://ublockorigin.com/lite)). | **İki tür ek koruma:** (1) Brave MV2 destek satırını `brave-core` içinde force-enabled yapar ([github.com/brave/brave-core/.../extension_features.cc](https://github.com/brave/brave-core/blob/master/chromium_src/extensions/common/extension_features.cc)); (2) Shields MV3'ten bağımsız çalıştığı için DNR kısıtları onu etkilemez ([brave.com/blog/brave-shields-manifest-v3](https://brave.com/blog/brave-shields-manifest-v3/)). |
| **Edge** | Standart MV3, Chromium lifecycle'ı korunur; Microsoft ayrı lifecycle dokümanı yayımlamaz ([learn.microsoft.com/.../manifest-v3](https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/manifest-v3)). | Edge kendi DNR limit dokümanı yayımlamaz; Chromium dokümanı referanstır ([developer.chrome.com/.../content-filtering](https://developer.chrome.com/docs/extensions/develop/concepts/content-filtering)). | uBO Lite çalışır ([ublockorigin.com/lite](https://ublockorigin.com/lite)); **tam (MV2) uBO çalışması Ağu 2026 tüketici geçişi ile kapanıyor** ([blogs.windows.com/msedgedev/...](https://blogs.windows.com/msedgedev/2026/08/07/moving-the-microsoft-edge-extensions-ecosystem-forward-with-manifest-version-3/)). | **IE mode etkileşimi:** IE sekmesinde sayfa içeriğiyle doğrudan etkileşen Edge uzantıları **desteklenmez** (Trident/MSHTML motoru, Chromium API uyumsuz); doğrulanmış Microsoft Q&A cevabı ([learn.microsoft.com/answers/questions/434363](https://learn.microsoft.com/en-us/answers/questions/434363/edge-brosers-does-ie-compatibility-mode-support-we), [learn.microsoft.com/deployedge/edge-ie-mode](https://learn.microsoft.com/en-us/deployedge/edge-ie-mode)). |
| **Vivaldi** | Standart MV3; Vivaldi MV3 kuralına Chromium'dan bağımsız kısıt koymaz ([vivaldi.com/blog/manifest-v3-update-...](https://vivaldi.com/blog/manifest-v3-update-vivaldi-is-future-proofed-with-its-built-in-functionality/)). | Chromium DNR limitleri geçerli (ayrı Vivaldi kotası dokümanı yok) ([developer.chrome.com/.../declarativeNetRequest](https://developer.chrome.com/docs/extensions/reference/api/declarativeNetRequest)). | **Tam uBO (MV2)** — Vivaldi MV2'yi "Chromium'da kaldığı sürece" destekleyeceğini açıkladı (resmi hedef Haz 2025) ([vivaldi.com/blog/manifest-v3-update-...](https://vivaldi.com/blog/manifest-v3-update-vivaldi-is-future-proofed-with-its-built-in-functionality/)). Güncel tartışmalar devam etmektedir ([forum.vivaldi.net/topic/112335](https://forum.vivaldi.net/topic/112335/will-the-end-of-manifest-v2-support-in-vivaldi-be-clearly-announced)). | **Sidebar/dock entegrasyonu ve yerleşik tracker+ad-blocker MV3 sınırlarından bağımsızdır**; hosts-format desteği (Vivaldi 6.8) eklendi ([vivaldi.com/blog/manifest-v3-update-...](https://vivaldi.com/blog/manifest-v3-update-vivaldi-is-future-proofed-with-its-built-in-functionality/)). |
| **Opera** | Standart MV3; Opera Chromium forks'unda lifecycle'ı değiştirmez ([blogs.opera.com/news/2025/09/mv2-extensions-opera](https://blogs.opera.com/news/2025/09/mv2-extensions-opera/)). | Chromium DNR limitleri geçerli; Opera-spesifik kota yok ([developer.chrome.com/.../content-filtering](https://developer.chrome.com/docs/extensions/develop/concepts/content-filtering)). | **Tam uBO (MV2) şu an çalışır** — Opera Haz 2026'da "MV2 destek politikası değişmedi" dedi ([piunikaweb.com/2026/06/16/opera-responds-chrome-mv2-ban](https://piunikaweb.com/2026/06/16/opera-responds-chrome-mv2-ban/)); store MV3'e dönüşecek, yeni MV2 kabul edilmiyor ([blogs.opera.com/news/2025/09/mv2-extensions-opera](https://blogs.opera.com/news/2025/09/mv2-extensions-opera/)). uBO Lite ayrıca kurulabilir ([ublockorigin.com/lite](https://ublockorigin.com/lite)). | **Sidebar entegrasyonu vendor'a özgü:** `sidebar_action` manifest anahtarı ile yan panel uzantıları (Opera 30+) ([help.opera.com/en/extensions/sidebar-action-api](https://help.opera.com/en/extensions/sidebar-action-api)); **yerleşik reklam engelleyici** MV2/MV3 kurallarından tamamen bağımsız çalışır ve uBO filtre listeleriyle uyumludur (May 2026 güncellemesi) ([piunikaweb.com/2026/06/16/opera-responds-chrome-mv2-ban](https://piunikaweb.com/2026/06/16/opera-responds-chrome-mv2-ban/)). |
| **Chrome-CFT** | Vanilya Chrome MV3 lifecycle'ı (service worker, host_permissions, content_scripts) aynıdır; resmi "testing" build'i, Puppeteer/Playwright/Selenium kurulumlarında standart yoldur ([groups.google.com/.../S0ET5wPjCAAJ](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/1-g8EFx2BBY/m/S0ET5wPjCAAJ)). | **Chrome DNR limit dokümanı birebir geçerli:** static 30k garanti + 300k global pool, 100 ruleset/50 enabled, dynamic 30k (safe 30k, non-safe 5k), regex 1000, disabled static 5000 ([developer.chrome.com/.../content-filtering](https://developer.chrome.com/docs/extensions/develop/concepts/content-filtering), [developer.chrome.com/.../declarativeNetRequest](https://developer.chrome.com/docs/extensions/reference/api/declarativeNetRequest), [MDN MAX_NUMBER_OF_REGEX_RULES](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/declarativeNetRequest/MAX_NUMBER_OF_REGEX_RULES)). | uBO Lite çalışır ([ublockorigin.com/lite](https://ublockorigin.com/lite)); **tam (MV2) uBO Chrome'da 2025 sonrası çalışmıyor** (MV2 Chrome Web Store'dan kaldırıldı; [brave.com/blog/brave-shields-manifest-v3](https://brave.com/blog/brave-shields-manifest-v3/)). | **"Test build" doğası gereği esnek uzantı politikası:** `--load-extension` yalnızca **markalı olmayan** build'lerde (Chrome for Testing, Chromium) açık kalır; Chrome 137+ markalı Chrome'da kaldırıldı, CFT aynı sürümde bu yeteneği korur ([groups.google.com/.../S0ET5wPjCAAJ](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/1-g8EFx2BBY/m/S0ET5wPjCAAJ)). Bu yüzden CFT "MV3 kısıtı testi" için doğru hedeftir: API Chrome ile aynı, kurulum yolu esnek. |

### DNR limitleri — sayısal referans (tüm Chromium vendorlar için geçerli kaynak tabanı)

| Kural tipi | Değer | Kaynak |
|---|---|---|
| Static rules (garanti) | 30.000 / uzantı | [developer.chrome.com/.../content-filtering](https://developer.chrome.com/docs/extensions/develop/concepts/content-filtering) |
| Static rules (global havuz) | 300.000 (tüm uzantılar için ortak) | [developer.chrome.com/.../content-filtering](https://developer.chrome.com/docs/extensions/develop/concepts/content-filtering) |
| Static ruleset sayısı | 100 tanımlı / 50 enabled | [developer.chrome.com/.../content-filtering](https://developer.chrome.com/docs/extensions/develop/concepts/content-filtering) |
| Dynamic rules (safe: block/allow/allowAllRequests/upgradeScheme) | 30.000 | [developer.chrome.com/.../content-filtering](https://developer.chrome.com/docs/extensions/develop/concepts/content-filtering) |
| Dynamic rules (non-safe: redirect vb.) | 5.000 (30k'nin içinde sayılır) | [developer.chrome.com/.../content-filtering](https://developer.chrome.com/docs/extensions/develop/concepts/content-filtering) |
| `regexFilter` kuralı (`MAX_NUMBER_OF_REGEX_RULES`) | 1000 (dynamic/session ile static kural dosyası ayrı ayrı değerlendirilir) | [MDN MAX_NUMBER_OF_REGEX_RULES](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/declarativeNetRequest/MAX_NUMBER_OF_REGEX_RULES) |
| Disabled static rule (`updateStaticRules`) | 5000 | [developer.chrome.com/.../declarativeNetRequest](https://developer.chrome.com/docs/extensions/reference/api/declarativeNetRequest) |

`.updateDynamicRules()` kural güncelleme API'si üç kural tipinin (dynamic/session/static) ortak
yöntemidir ve limit aşımında kota hatası üretir; runtime'da kullanıcı tanımlı kurallar için
maksimum 30.000 custom rule sınırı geçerlidir
([developer.chrome.com/.../declarativeNetRequest](https://developer.chrome.com/docs/extensions/reference/api/declarativeNetRequest),
[developer.chrome.com/.../content-filtering](https://developer.chrome.com/docs/extensions/develop/concepts/content-filtering)).

---

## 3. Bilinen uyumluluk sorunları (özet)

- **Chrome / Chrome-CFT:** Tam (MV2) uBlock Origin artık çalışmıyor; MV2 Chrome Web Store'dan
  kaldırıldı ([brave.com/blog/brave-shields-manifest-v3](https://brave.com/blog/brave-shields-manifest-v3/)).
  Bunun yerine uBO Lite (MV3) kullanılır; ancak MV3 kural limitleri (yukarıdaki tablo) yüzünden
  MV2'deki tam filtre kapasitesine erişemez
  ([ublockorigin.com/lite](https://ublockorigin.com/lite)).
- **Chrome-CFT + `--load-extension`:** Chrome 137+ markalı Chrome'da bu bayrak kaldırıldı; CFT
  bu bayrağı koruduğu için otomasyon/extension-test iş yükleri CFT'ye kaydı
  ([groups.google.com/.../S0ET5wPjCAAJ](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/1-g8EFx2BBY/m/S0ET5wPjCAAJ)).
- **Edge:** Ağu 2026 itibarıyla MV2 tüketici geçişi başladı, hedef 2026 sonu; tam (MV2) uBO bu
  süreçte devre dışı kalır, kurumsal cihazlar bu geçişin dışında tutulur
  ([blogs.windows.com/msedgedev/...](https://blogs.windows.com/msedgedev/2026/08/07/moving-the-microsoft-edge-extensions-ecosystem-forward-with-manifest-version-3/)).
- **Edge IE mode:** IE sekmesinde içerikle doğrudan etkileşen Edge uzantıları çalışmaz
  ([learn.microsoft.com/answers/questions/434363](https://learn.microsoft.com/en-us/answers/questions/434363/edge-brosers-does-ie-compatibility-mode-support-we)).
- **Brave / Vivaldi / Opera:** MV2 tam uBO hâlâ çalışır (Brave: vendor-hosted 4 uzantı;
  Vivaldi: Chromium'da kaldığı sürece; Opera: Haz 2026 beyanı ile korunuyor)
  ([brave.com/blog/brave-shields-manifest-v3](https://brave.com/blog/brave-shields-manifest-v3/),
  [vivaldi.com/blog/manifest-v3-update-...](https://vivaldi.com/blog/manifest-v3-update-vivaldi-is-future-proofed-with-its-built-in-functionality/),
  [piunikaweb.com/2026/06/16/...](https://piunikaweb.com/2026/06/16/opera-responds-chrome-mv2-ban/)).

---

## 4. Bizim `extension_host` için: hangi vendor hangi testi doğrular?

Bu deponun `ExtensionHost` sözleşmesi (izole kapsül, sağlam karar toplama) ile yukarıdaki
gerçek vendor davranışını eşleştiren testler (`tests/test_extension_host.py`,
`tests/test_mv3_surface.py`) ve karşılığı:

| Vendor davranışı | Doğruladığı test / sözleşme | Not |
|---|---|---|
| **Chrome-CFT** (düz MV3+DNR yüzeyi, esnek kurulum) | `test_manifest_dnr_rules_translates_to_engine_rules`, `test_build_extension_engine_blocks_extension_rule`, `test_manifest_requires_mv3` | CFT, MV3/DNR'nin en "düz" uygulaması olduğundan `mv3_surface.py`'nin standart referansıdır. |
| **Brave** (izole MV2 + Shield koruması) | `test_extensions_are_isolated_from_each_other`, `test_one_failing_extension_does_not_break_host_or_siblings` | Brave'in ek koruma katmanı, ExtensionHost'un "izole kapsül" garantisiyle aynı doğrultudadır. |
| **Opera** (sidebar + yerleşik engelleyici) | `test_attach_extension_and_decide`, `test_host_allows_when_no_extension_matches` | Opera'nın yerleşik engelleyicisi ve `sidebar_action` uzantıları aynı anda çalıştığından karar toplama testi birebir doğrulanır. |
| **Edge** (IE mode kısıtı, MV2 geçişi) | `test_disable_re_enables_single_extension`, `test_detach_removes_only_that_extension` | IE sekmesinde devre dışı/eksik çalışan uzantı, bizim host'ta "tek uzantıyı etkisizleştirme" sözleşmesine denk gelir. |
| **Vivaldi** (MV2 sürekliliği + yerleşik engelleyici) | `test_extensions_are_isolated_from_each_other`, `test_duplicate_names_rejected`, `test_attach_is_idempotent_per_name_listing` | Vivaldi'nin uzun MV2 destek penceresi, aynı host'ta çok uzantı barındırma/çakışma yönetimi senaryosunu test eder. |

---

## 5. Kaynakça (özet)

1. [developer.chrome.com — Content filtering](https://developer.chrome.com/docs/extensions/develop/concepts/content-filtering)
2. [developer.chrome.com — declarativeNetRequest API](https://developer.chrome.com/docs/extensions/reference/api/declarativeNetRequest)
3. [MDN — MAX_NUMBER_OF_REGEX_RULES](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/declarativeNetRequest/MAX_NUMBER_OF_REGEX_RULES)
4. [groups.google.com — PSA: Removing `--load-extension` flag in Chrome branded builds](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/1-g8EFx2BBY/m/S0ET5wPjCAAJ)
5. [blogs.windows.com — Moving the Microsoft Edge extensions ecosystem forward with MV3](https://blogs.windows.com/msedgedev/2026/08/07/moving-the-microsoft-edge-extensions-ecosystem-forward-with-manifest-version-3/)
6. [learn.microsoft.com — Timeline for migrating to Manifest V3](https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/manifest-v3)
7. [learn.microsoft.com — IE mode](https://learn.microsoft.com/en-us/deployedge/edge-ie-mode)
8. [learn.microsoft.com Q&A — Edge extensions in IE mode](https://learn.microsoft.com/en-us/answers/questions/434363/edge-brosers-does-ie-compatibility-mode-support-we)
9. [brave.com — What Manifest V3 means for Brave Shields](https://brave.com/blog/brave-shields-manifest-v3/)
10. [vivaldi.com — Manifest v3 update](https://vivaldi.com/blog/manifest-v3-update-vivaldi-is-future-proofed-with-its-built-in-functionality/)
11. [help.opera.com — Opera Sidebar Action API](https://help.opera.com/en/extensions/sidebar-action-api)
12. [blogs.opera.com — MV2 extensions on Opera](https://blogs.opera.com/news/2025/09/mv2-extensions-opera/)
13. [piunikaweb.com — Opera responds on Chrome MV2 ban](https://piunikaweb.com/2026/06/16/opera-responds-chrome-mv2-ban/)
14. [ublockorigin.com/lite — uBlock Origin Lite](https://ublockorigin.com/lite)
