# REA Hedef: Eklenti Mağazaları & Native Entegrasyon Yüzeyi

> Kaynak: mağaza geliştirici dokümanları, MV3 mimari rehberleri (2026). Amaç:
> ürünün "native eklenti desteği" iddiasını hangi mağaza/protokol düzeyinde
> karşılayacağını dürüstçe belirlemek. Tüm akışlar okuma/derleme düzeyindedir;
> hesap oluşturma/yükleme yapılmadı.

## 1. Mağaza karşılaştırması (2026-10)

| Mağaza | Hesap ücreti | İnceleme | Güncelleme | MV2 durumu | İmzalama |
|---|---|---|---|---|---|
| **Chrome Web Store (CWS)** | $5 (tek seferlik) | 1-7 gün | otomatik (manifest sürümü) | **31.08.2026'da son MV2 listeleri kaldırıldı** — MV3-only | Google sunucu tarafı imzalar |
| **Edge Add-ons** | Ücretsiz (Partner Center) | 1-7 gün | otomatik | MV3-only (Chromium) | Microsoft imzalar |
| **Firefox AMO** | Ücretsiz | 1-5 gün (insan) | otomatik | **MV2 blocking webRequest korunur** (reklam engelleyiciler için) | Mozilla imzalar; kaynak kod zorunlu |
| **Opera Addons** | Ücretsiz | 1-7 gün | otomatik | Chromium; `.crx` + **`.nex` imzalı Opera biçimi** | Opera imzalar |
| **Safari App Store** | Apple Developer | App Store inceleme | App Store | MV3 kısmi; `safari-web-extension-converter` + macOS build zorunlu | Apple sertifikası |

## 2. Teknik farklar (native destek için)

| Yüzey | Chrome/Edge/Opera (Blink) | Firefox (Gecko) | Safari (WebKit) |
|---|---|---|---|
| Background | Service Worker (30s ömür) | Event page (`background.scripts`) | `backgroundScripts` |
| Ağ engelleme | `declarativeNetRequest` (webRequest blocking **yok**) | webRequest blocking **korunur** + DNR | DNR (kısmi) |
| Namespace | `chrome.*` | `browser.*` + `chrome.*` | `browser.*` (Promise) |
| Side Panel | `sidePanel` API | `sidebarAction` | kısmi |
| Offscreen | `chrome.offscreen` (Chrome/Edge) | **yok** (degrade edilmeli) | kısmi |
| Özel alan | gerekmez | `browser_specific_settings.gecko.id` **zorunlu** | — |
| Veri toplama beyanı | dashboard formu | `data_collection_permissions` **zorunlu** (3 Kasım 2025+) | App Store gizlilik etiketi |

### MV3 kotalar (native destek için sınırlar)
- Statik DNR kuralı: 30.000/eklenti; 330.000 tümü (EasyList'in 1M+ kuralı sığmaz
  → uBlock Origin MV3'te kısıtlı).
- Dinamik kural: 5.000 (bunların 5.000'i "güvensiz" tip: redirect vb.).
- Oturum kuralı: 5.000 (tarayıcı çıkışıyla sıfırlanır).
- **Uzak kod yasak**: tüm JS paket içinde olmalı; yalnızca User Scripts API gibi
  belgelenmiş arayüzlerden uzak mantık çalışabilir.

## 3. "Native eklenti desteği" iddiasının dürüstlüğü

Ürünün (AI-Native Browser Engine) eklenti desteğini "native" diye sunabilmesi
için gereken asgari:

1. **MV3 tam uyum** — CWS/Edge/Opera/PWA üstünde çalışan her paket bizde de
   çalışmalı (service worker ömür yönetimi, offscreen degrade, DNR).
2. **Firefox yüzeyi ayrı** — `gecko.id` + `data_collection_permissions` +
   blocking webRequest için ayrı manifest override (tek kod tabı, iki build).
3. **İmzalama/doğrulama** — kendi mağazamız yoksa CWS `clients2.google.com/
   service/update2/crx` güncelleyicisine bağımlı kalırız; kendi bileşen
   kanalını kurmak (CRX3 doğrulaması + kendi imza anahtarı) "native" iddiasının
   gereği. Bu, REA'da Opera `.nex` (imzalı özel paket) örneğiyle destekleniyor.
4. **Şeffaflık** — her eklenti için `manifest.json` izin envanteri + giden uç
   listesi (`discover_network_endpoints` ile) otomatik raporlanmalı. CWS'in
   "dar izin" kuralı bizim için de geçerli: kullanılmayan izin = ret sebebi.

## 4. Mağaza politikası (ret sebepleri — bizim için kontrol listesi)

- **Tek amaç** ("single purpose"): her eklenti tek ve dar bir amaca sahip olmalı.
- **En dar izin**: kullanılmayan `permissions`/`host_permissions` hızlı ret yolu.
- **`<all_urls>` / `*://*/*`**: açık gerekçe istenir, aksi halde ret.
- **Gizlilik politikası**: HTTPS, sabit URL, düz dil (yer tutucu reddedilir).
- **Kaynak kod**: AMO, minify/bundle edilmiş paketle birlikte okunabilir
  `source.zip` + `BUILD.md` (bit-bit tekrarlanabilir derleme) ister.
- **İzin gerekçesi**: "eklenti çalışması için gerekiyor" tüm mağazalarda ret.

## 5. Ürün için somut çıkarımlar

1. **CWS MV3-only** (31.08.2026) → bizim için de MV3 taban zorunlu; MV2 legacy
   destek taşımak gereksiz yük.
2. **Blocking webRequest = rekabet boşluğu**: CWS/Edge bunu kaldırdı, Firefox
   koruyor. Bizim motor "MV3 + blocking yüzey" sunarsa engelleme/gizlilik
   eklentileri için **tek Chromium-temelli sığınak** oluruz (uBlock benzeri).
3. **Kendi güncelleme kanalı**: CWS `clients2.google.com` CRX updater yerine/a
   yanına kendi (imzalı) bileşen kanalı — Opera `.nex` modeli.
4. **MV3 kotları**: 30k statik kural sınırını aşan engelleme listeleri için
   kendi kural motoru (reklam engelleyici sınıfı) farklılaştırıcı olabilir.
5. **Firefox build'i** ayrı manifest override ile sürdür; `gecko.id` değişirse
   kullanıcı verisi yetim kalır (AMO'ya özgü tuzak).
