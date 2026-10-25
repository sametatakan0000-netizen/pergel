# REA Sentetik Konumlandırma — "Nerede Kazanırız / Nerede Kaybederiz"

> Bu doküman, `docs/rea/` altındaki tüm hedef REA'larının (5 Chromium çatalı +
> 4 OS/ISO) tek konumlandırma tablosuna indirgenmiş halidir. Amaç: ürünün
> (AI-Native Browser Engine SaaS) pazardaki SOTA konumunu dürüstçe belirlemek.
> Kaynak her hedefin `<target>.md` dosyasıdır; sayılar oradan türetilmiştir.

## 1. Patch-lag tablosu (en sert farklılaştırıcı)

| Hedef | Ürün sürümü | Chromium temeli | V8 | CFT'e göre major fark |
|---|---|---|---|---|
| Chrome for Testing | 156.0.8078.47 | 156 | 15.6 | 0 |
| Edge | 156.0.4314.42 | 156 | 15.6 | 0 |
| Opera | 138.0.6044.24 | 154 | 15.4 | 2 |
| Vivaldi | 8.2.4133.94-1 | 152 | 15.2 | 4 |
| Brave | 1.52.126 | 114 | 11.4 | **42** |

**Konumlandırma etkisi:** Chromium tabanlı otomasyon ürünlerinde en kritik risk
sinyali *patch-lag*'dir. Brave 42 major geride — bu, ürünün güvenlik/rekabet
tablosunda açıkça vurgulanması gereken tek en büyük aykırı değer. Kendi
motorumuz CFT/Edge düzeyinde (0 major lag) konumlanıyorsa "güvenli otomasyon
yüzeyi" iddiası savunulabilir; altında herhangi bir fork için iddia edilemez.

## 2. Otomasyon yüzeyi (CDP/WebDriver)

| Hedef | CDP DevTools | Not |
|---|---|---|
| Chrome for Testing | açık (`--remote-debugging-port`) | referans davranış |
| Edge | açık | CDP ile UA/V8 üçlü doğrulaması yapıldı |
| Opera | açık | aynı Chromium CDP |
| Vivaldi | **kapalı/takılı** | stok Chromium'dan farklı; DevTools bayrağı dinamik doğrulama bekliyor |
| Brave | açık | CDP ile 114 tabanı doğrulandı |
| Ubuntu 26.04.1 | geckodriver + `firefox.geckodriver` | deb Chromium yok; otomasyon Firefox/snap üzerinden |

**Konumlandırma etkisi:** Otomasyon için *güvenilir* CDP yüzeyi şart. Vivaldi
tarzı "kapalı varsayılan" çatallar, otomasyon ürünlerinde doğrudan dışlanır.
Kendi motorumuz için CDP'nin **açık ve kararlı** olduğu garanti edilmeli (ürünün
ana değer önerisi).

## 3. Güncelleme mekanizması (supply-chain yüzeyi)

| Hedef | Güncelleme yolu | Üçüncü taraf uçlar |
|---|---|---|
| CFT / Edge / Brave / Vivaldi | CRX bileşen servisi `clients2.google.com/service/update2/crx` | Widevine, MEI (MV2) |
| Opera | gömülü `opera_autoupdate` 1.3.0 | `cashback.opera.com` |
| Vivaldi | `update-ffmpeg` + `update.vivaldi.com` | `go.mail.ru`, `suggests.go.mail.ru` |
| Windows 11 | AppX provizyon + Store | `ContentDeliveryManager` (bloat geri yükleyici) |

**Konumlandırma etkisi:** Opera/Vivaldi ikili içine gömülü arama/monetizasyon
anlaşmaları (`go.mail.ru`) tedarik-zinciri riski olarak listelenmeli. Bizim
motorumuzda böyle gömülü üçüncü taraf uç bulunmaması (varsa şeffafça listelenmesi)
avantaj. Windows'ta `ContentDeliveryManager` kapatılmazsa debloat kalıcı olmaz.

## 4. Bloatware / gereksiz yüzey (OS/ISO)

- **Windows 11 26300:** 185 AppX paketi, 23'ü kaldırılabilir tüketici bloatware'i
  (Copilot, Bing*, Xbox*, Clipchamp, ZuneMusic, Teams, ...).
- **Ubuntu 26.04.1:** 13 snap; Firefox 154 snap olarak; deb Chromium yok.
- **Fedora 44:** snapd yok; Firefox 150 RPM; 1982 paket; EROFS (`squashfs.img`
  ismine rağmen).
- **Alpine 3.24.3:** minimal (370 MB ISO), modloop tabanlı.

**Konumlandırma etkisi:** Hafif/imalat temiz taban (Alpine/Fedora modeli) ile
"hızlı, şişkinlikten arınmış otomasyon" iddiası eşleştirilebilir; Windows hedef
ortamı ise debloat gerektirir.

## 5. Nerede kazanırız / Nerede kaybederiz (dürüst)

**Kazanırız (savunulabilir iddialar):**
1. *Patch-lag:* CFT/Edge düzeyinde (0 major) Chromium temeli kullanılırsa,
   Brave/Opera/Vivaldi'nin önünde güvenlik konumu.
2. *Temiz otomasyon yüzeyi:* Vivaldi'nin aksine açık/stabil CDP; gömülü üçüncü
   taraf arama/monetizasyon uçları yok.
3. *Şeffaf bileşen envanteri:* MV2/MV3 bileşenleri (Widevine, MEI) açıkça
   listelenir; gizli updater yok.

**Kaybederiz (kabul etmemiz gereken):**
1. *Market erişimi:* Brave/Opera/Vivaldi'nin hazır kullanıcı tabanı ve marka
   güveni yok; biz yeni giriyoruz.
2. *Codec/patent:* Vivaldi `update-ffmpeg` ile tescilli codec sunar; bizim
   motorumuz bunu varsayılan sunmaz (yasal/stratejik kısıt).
3. *Ekosistem:* Chrome Web Store MV3 eklenti uyumu tam desteklenmedikçe geniş
   eklenti kütüphanesi karşısında dezavantaj.

## 6. Ürün için somut çıkarımlar

1. **Güvenlik tablosuna `patch-lag` sütunu ekle** (Brave 42 major öneki örnek).
2. **CDP kararlılığını garanti et** — "her sürümde açık DevTools" ürün SLA'sı.
3. **Gömülü üçüncü taraf uç envanteri** üretimde otomatik raporlanmalı
   (`discover_network_endpoints` çıktısı) — Opera/Vivaldi `go.mail.ru` örneği.
4. **MV3 geçiş + bileşen güncelleme** şeffaflığı: CRX kanalı yerine kendi
   bileşen kanalını (varsa) açıkça belgele.
5. **Hedef-ortam hazırlığı:** Windows için kalıcı debloat (WIM-mount), Linux için
   Alpine/Fedora-temelli hafif imaj önerisi.
