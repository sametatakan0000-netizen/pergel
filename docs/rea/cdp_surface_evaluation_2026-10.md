# CDP Yüzey Değerlendirmesi — Brave, Edge, Vivaldi, Opera, Chrome for Testing (Ekim 2026)

**Kapsam:** Beş Chromium-alemi vendor'un CDP (Chrome DevTools Protocol) yüzeyi — domain
kapsamı, port/bindings varsayılanları, headless farkları, ölçülmüş/kanıtlanmış sınırlamalar.
**Kural:** `docs/rea/README.md` (observe-only varsayılan, sorumlu disclosure). Bu doküman
yeni fikir/öneri üretmez; yalnızca ölçülebilir, kaynağı URL'li durumları kaydeder. Repo içi
ölçümler `docs/rea/*.md` + `docs/rea/data/*.json` + bench çıktılarından; web iddiaları Ekim
2026'da doğrulanmış kaynaklardan (anahtar web kaynakları 2026-10-27'de yeniden doğrulandı).

**Repo sürüm notu (dürüstlük):** depodaki ölçümler 2026-10-25 apt paketleriyle yapıldı
(Brave 1.52.126 / Chromium 114, Edge 156.0.4314.42, Vivaldi 8.2.4133.94, Opera
138.0.6044.24, CFT 156.0.8078.47). Ekim 2026 sonu itibarıyla güncel vendor sürümleri
farklıdır (bkz. ilgili satırlar); patch-lag karşılaştırmaları hangi sürümün ölçüldüğüyle
birlikte okunmalıdır.

---

## 1. Vendor başına tek satır başlık

- **Chrome for Testing (Google):** CDP'nin referans implementasyonu, 9/9 domain tam +
  otomasyon için tasarlanmış tek build; risk notu: 136+'ta `--remote-debugging-port`
  yalnızca non-default `--user-data-dir` ile çalışır (kayıtlı profil hırsızlığına karşı),
  port yine de kimliksiz localhost dinler.
- **Brave (Brave Software):** stok Chromium CDP yüzeyi tam (114 tabanlı ölçülen paket dahil,
  güncel satır 154 tabanlı) ve remote debugging varsayılan-proxied açık; risk notu: repo
  ölçümünde **42 major patch-lag** (Chromium 114) — CDP yüzeyi olgun, güvenlik tazeliği değil.
- **Microsoft Edge:** CDP Chrome ile **API-eşdeğer** (Microsoft'un kendi dokümanı), ek olarak
  enterprise politika katmanı (`RemoteDebuggingAllowed`, `DeveloperToolsAvailability*`) ile
  CDP'yi politika üzerinden kısma imkânı; risk notu: policy-managed kurumsal yüzey — REA'da
  politika konfigürasyonu sonucu değiştirebilir.
- **Vivaldi (Vivaldi Software):** CDP yüzeyi **en olgun olmayan** vendor — repo bench probe'ı
  "Vivaldi does not expose the CDP DevTools port when launched" bulgusu üretti; bağımsız
  üçüncü taraf doğrulaması flatten session-level komutların cevapsız olduğunu bildiriyor;
  kendi forumları da headless'ın "implemented değil" olduğunu söylüyor. Risk notu: otomasyon
  yüzeyi kapalı/tekinsiz.
- **Opera (Opera Software):** stok Chromium CDP + **resmi** `opera-devtools-mcp`
  (chrome-devtools-mcp fork'u) — vendor kendi CDP otomasyonunu ilk elden destekliyor;
  risk notu: `opera_autoupdate` gibi vendor-özel updater ve gömülü monetizasyon yüzeyi
  (repo: `go.mail.ru`) CDP dışı saldırı yüzeyi olarak not edildi.

---

## 2. Karşılaştırma tablosu

### 2.1 Domain coverage (Page, Network, Target, Runtime, DOM, Input, Emulation, Security, Debugger)

| Vendor | Page | Network | Target | Runtime | DOM | Input | Emulation | Security | Debugger | Not |
|---|---|---|---|---|---|---|---|---|---|---|
| Chrome for Testing | ✔ tam | ✔ tam | ✔ tam | ✔ tam | ✔ tam | ✔ tam | ✔ tam | ✔ tam | ✔ tam | Referans implementasyon; `/json/protocol` ile build'e özel şema doğrulanabilir ([chromedevtools.github.io/devtools-protocol](https://chromedevtools.github.io/devtools-protocol/)) |
| Brave | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | Stok Chromium domain seti; repo CDP probe'ı 3'lü (Browser/UA/V8) doğrulama yaptı (`docs/rea/brave.md`) |
| Edge | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | Microsoft: "Edge DevTools Protocol matches the APIs of the Chrome DevTools Protocol" ([learn.microsoft.com](https://learn.microsoft.com/en-us/microsoft-edge/test-and-automation/devtools-protocol)); bağımsız doğrulama: "identical to Chrome on CDP" — Chrome 154.x / Edg 140.x üzerinde ölçülmüş ([npmjs cdp-browser-mcp](https://www.npmjs.com/package/cdp-browser-mcp)) |
| Opera | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | Resmi `opera-devtools-mcp` (chrome-devtools-mcp fork) CDP üzerinden trace/performance/UI dahil sürüyor ([github.com/operasoftware/opera-devtools-mcp](https://github.com/operasoftware/opera-devtools-mcp)) |
| Vivaldi | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ | **Doğrulanmış sapma:** flatten session-scoped komutlar (`Runtime.enable` gibi) cevap vermiyor, yalnızca browser-level komutlar; non-flatten workaround var ama bağlı değil ([npmjs cdp-browser-mcp](https://www.npmjs.com/package/cdp-browser-mcp), 2026-10-27 doğrulandı). Repo bench: port hiç açılmadı (`docs/rea/vivaldi.md:28`, `positioning-synthesis.md` §2) |
| Lightpanda (Zig/V8, karşılaştırma) | ◐ | ◐ | ✔ | ✔ | ✔ | ◐ | ✘ | ◐ | ✘ | 17 domain implemente; `Emulation`, `Page.captureScreenshot`, `Page.printToPDF` yok (render motoru yok); Debugger yok; `Network`/`CSS`/`Log` kısmi ([docs.bswen.com 2026-03-19](https://docs.bswen.com/blog/2026-03-19-lightpanda-cdp-puppeteer-playwright), [armory compatibility.md](https://github.com/Mathews-Tom/armory/blob/main/skills/lightpanda-browser/references/compatibility.md)) |

Çekirdek gerçek: CDP domain'leri Chromium ağacında `browser_protocol.pdl` + `js_protocol.pdl`
olarak tanımlanır ve aynı ağaçtan üretilir; bir Chromium fork'u bilerek çıkarmadıkça domain
seti aynıdır ([chromedevtools.github.io/devtools-protocol](https://chromedevtools.github.io/devtools-protocol/) —
"canonical protocol definitions live in the Chromium and V8 source trees"). Bu yüzden Brave/
Edge/Opera satırlarında fark **domain varlığı**nda değil, **port/oturum davranışı**nda ve
vendor politikalarındadır; Vivaldi tek ölçülmüş istisnadır.

### 2.2 Port binding / bindings varsayılanları

| Vendor | Varsayılan port açığı | Bind davranışı & güvenlik katmanı | Kaynak |
|---|---|---|---|
| Chrome / CFT | Hayır — `--remote-debugging-port` gerekli | 136+: default user-data-dir ile flag **görmezden gelinir**, `--user-data-dir` zorunlu. CFT bu kısıtlamadan muaf (Google'ın otomasyon önerisi). HTTP `Host` header doğrulaması (DNS rebinding), `--remote-allow-origins` WS Origin kontrolü. `webSocketDebuggerUrl` desktop'ta tahmin edilemez UUIDv4 taşır | [developer.chrome.com/blog/remote-debugging-port](https://developer.chrome.com/blog/remote-debugging-port), [CDP spec — Security and origin restrictions](https://chromedevtools.github.io/devtools-protocol/) |
| Chrome/Edge/Brave ortak (144+) | Hayır | `chrome://inspect/#remote-debugging` (Brave: `brave://inspect`, Edge: `edge://inspect`) ile kullanıcı onaylı mod: HTTP discovery endpoint'leri 404 döner, bağlantı başına **"Allow remote debugging?"** prompt'u çıkar; kalıcı "always allow" yok, `RemoteDebuggingAllowed` politikası yalnızca tümüyle aç/kapa | [pedrosatin.com (2026-10-07, Brave üzerinde ölçülmüş)](https://pedrosatin.com/en/blog/brave-remote-debugging-authorization), [dev-newb/yes-dev](https://github.com/dev-newb/yes-dev) |
| Brave | Hayır (flag ile localhost) | 2020'de remote debugging **default proxied + enabled** yapıldı (brave-core #5500). Bayrakla açılan port kimliksizdir: aynı kullanıcıdaki herhangi bir süreç `curl /json/version` ile WebSocket adresine ulaşıp cookie okuyabilir (ölçülmüş) | [brave-core PR #5500](https://github.com/brave/brave-core/pull/5500), [pedrosatin.com](https://pedrosatin.com/en/blog/brave-remote-debugging-authorization) |
| Edge | Hayır (flag ile localhost) | Chrome 136 kısıtlaması Edge'de de görünür (default profil ile CDP bağlanmıyor, Microsoft Q&A raporu). Ekstra: `RemoteDebuggingAllowed` (desktop ≥93, Android ≥156) ile remote debugging tamamen kapatılabilir; `DeveloperToolsAvailability` (+Allow/Blocklist) **doğrudan CDP bağlantılarını ve `chrome.debugger` API'yi** de kapsar | [RemoteDebuggingAllowed](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/remotedebuggingallowed), [DeveloperToolsAvailability](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/developertoolsavailability), [MS Q&A](https://learn.microsoft.com/en-au/answers/questions/5976829/microsoft-edge-remote-debugging-is-not-working-whe) |
| Opera | Hayır (flag ile localhost) | `--remote-debugging-port` startup-only'dur; normal açılmış Opera'ya **sonradan bağlanılamaz**. `DevToolsActivePort` dosyası attach keşfi için kullanılır (resmi CLI invariant'ı) | [operasoftware/opera-browser-cli CLAUDE.md](https://github.com/operasoftware/opera-browser-cli/blob/main/CLAUDE.md) |
| Vivaldi | Hayır — ve repo'da flag ile de açılmadı | Repo bench probe'ı: launch'ta CDP port yok ("BLOCKED: no CDP DevTools port"). Forumlarda `--remote-debugging-port=2015` ile localhost:2015'e erişim "doesn't work anymore for some reason" olarak raporlanmış; bir kullanıcı crconsole ile başlattıktan sonra Vivaldi'nin cevap vermediğini belirtiyor | `docs/rea/vivaldi.md:28`, [forum.vivaldi.net/topic/27916](https://forum.vivaldi.net/topic/27916/access-local-host-for-modding), [forum.vivaldi.net/topic/34521](https://forum.vivaldi.net/topic/34521/linux-changing-theme-via-command-line/23) |

**Vivaldi'nin CDP portunu açmaması — kanıt durumu (ölçülebilir olanlar):**
1. **Repo ölçümü (birincil):** bench harness probe'ı iki bağımsız koşuda Vivaldi'yi
   başlatırken CDP DevTools portu bulamadı — `docs/rea/vivaldi.md:28` ("our bench probe
   earlier reported 'vivaldi BLOCKED: no CDP DevTools port on launch'"),
   `docs/rea/positioning-synthesis.md` §2 tablosu ("Vivaldi | blocked: no CDP port").
2. **Bağımsız üçüncü taraf:** bir CDP tabanlı MCP aracı yazarı Vivaldi'nin `flatten`
   session-scoped komutlara (`Runtime.enable` vb.) hiç cevap vermediğini, yalnızca
   browser-level komutlara yanıt döndüğünü raporlar ([npmjs cdp-browser-mcp](https://www.npmjs.com/package/cdp-browser-mcp)).
3. **Kullanıcı raporları:** Vivaldi forumlarında `--remote-debugging-port` ile açılan
   portun "doesn't work anymore" olduğu, crconsole başlatımının cevapsız kaldığı yazıyor
   ([forum.vivaldi.net/topic/27916](https://forum.vivaldi.net/topic/27916/access-local-host-for-modding)).
4. **Yapısal gözlem (iddia değil):** Vivaldi UI'si Chromium Views yerine Web tabanlı
   overlay + browser-process hook'u ile inşa edilir; DevTools sunucusunun Vivaldi süreç
   modelinde beklenen bind noktasını yapmaması için yapısal bir olasılık sunar
   ([deepwiki vivaldi architecture](https://deepwiki.com/cedricschwyter/vivaldi/3-core-browser-architecture)).
   "Engeli kesin olarak bu mekanizmadır" **iddia edilmez** — kesin mekanizma doğrulanmış
   değildir.

### 2.3 Headless mod farkları

| Vendor | Headless durumu | Not / kaynak |
|---|---|---|
| Chrome / CFT | ✔ Tam. `--headless` = full browser binary (112+ "new headless"); `chrome-headless-shell` ayrı, hafif binary (M118+ CFT altyapısından iner). **Chrome 132 `--headless=old`'u kaldırdı** — artık hata basar | [chromium headless README](https://chromium.googlesource.com/chromium/src/+show/lkgr/headless/README.md), [developer.chrome.com chrome-headless-shell](https://developer.chrome.com/blog/chrome-headless-shell) |
| CFT / headless-shell tespit farkı | headless-shell üçüncü bir JA4 TLS parmak izi, hiç `Accept-Language` göndermez, UA'da tam sürüm, `window.chrome` yok, PDF viewer/plugin yok — CDP yüzeyi aynı ama ağ/gözlemlenebilir yüzey farklı | [clearcotelabs.com/chrome-for-testing (154.0.8037.57 üzerinde ölçülmüş)](https://clearcotelabs.com/chrome-for-testing) |
| Brave / Edge / Opera | Chromium headless davranışını miras alır; vendor-özel headless kısıtı belgelenmedi (ölçülmedi — iddia yok) | — |
| Vivaldi | ✘ **Yok.** "Commandline for headless mode and screen capture does not work in Vivaldi as it is not implemented" | [forum.vivaldi.net/topic/112526](https://forum.vivaldi.net/topic/112526/question-headless-mode) |
| Lightpanda | Headless-only zaten; render motoru olmadığından screenshot/PDF üretilemez | [armory compatibility.md](https://github.com/Mathews-Tom/armory/blob/main/skills/lightpanda-browser/references/compatibility.md) |

### 2.4 Tespit edilen bilinen sınırlamalar (vendor bazında)

| Vendor | Sınırlama (ölçülmüş/kanıtlanmış) | Kaynak |
|---|---|---|
| CFT | Default `--user-data-dir` ile CDP flag'leri geçersiz (136+); test field-trial config'i TLS JA4'ü değiştirir (t13d1518h2…), `--disable-field-trial-config` ile normale döner; "for testing" infobar | [developer.chrome.com](https://developer.chrome.com/blog/remote-debugging-port), [clearcotelabs](https://clearcotelabs.com/chrome-for-testing) |
| Brave | Repo ölçümü: apt stable paketi Chromium **114** tabanı (CFT/Edge 156'ya göre 42 major geride) — CDP domain seti 114 seviyesinde donmuş; ayrıca farbling (canvas/audio per-session rastgeleleştirme) engine-level farklılık üretir, CDP'den değil | `docs/rea/brave.md`, [invisible_playwright comparison](https://github.com/feder-cr/invisible_playwright/blob/main/docs/alternative-chromium-browsers-for-automation.md) |
| Edge | CDP Chrome ile eşdeğer, ama `DeveloperToolsAvailability*` politikaları CDP bağlantılarını ve `chrome.debugger`'ı hedef bazda kısabilir — kurumsal imajlarda yüzey daralır | [learn.microsoft.com](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/developertoolsavailability) |
| Opera | `--remote-debugging-port` startup-only (sonradan attach yok); normal kullanıcı profili ile Chrome 136 kısıtlaması aynı şekilde geçerli | [opera-browser-cli](https://github.com/operasoftware/opera-browser-cli/blob/main/CLAUDE.md) |
| Vivaldi | (a) Repo: launch'ta CDP port açılmadı. (b) flatten session-scoped komutlar cevapsız (yalnız browser-level). (c) headless implemente değil. (d) Claude uzantısı gibi CDP-tabanlı araçlar Vivaldi'de çalışmıyor (uzun süreli, kullanıcı raporlu bug; vendor "looking into it" dedi) | `docs/rea/vivaldi.md:28`, [npmjs cdp-browser-mcp](https://www.npmjs.com/package/cdp-browser-mcp), [forum.vivaldi.net/topic/111283](https://forum.vivaldi.net/topic/111283/bug-report-claude-extension-for-chrome-not-working-in-vivaldi-browser/99?page=3) |
| Vivaldi (mimari not) | Vivaldi UI'si Chromium Views yerine Web tabanlı bir overlay; Chromium browser process'i hook'lanarak genişletilmiş. Bu, DevTools/CDP yüzeyinin stok davranıştan sapması için yapısal bir açıklık — ancak "engeli bu kesinleştirir" **iddiası değil**, yalnızca kaynaklı mimari gözlem | [deepwiki vivaldi architecture](https://deepwiki.com/cedricschwyter/vivaldi/3-core-browser-architecture) |
| Lightpanda | CDP 17 domain ama `Emulation`, `Debugger`, `Overlay`, `Animation`, `Media`, `WebAuthn` yok; `Page.captureScreenshot`/`printToPDF` yok; Playwright'un dinamik feature-detection'ı bazı varsayımlarda başarısız | [docs.bswen.com](https://docs.bswen.com/blog/2026-03-19-lightpanda-cdp-puppeteer-playwright), [armory](https://github.com/Mathews-Tom/armory/blob/main/skills/lightpanda-browser/references/compatibility.md) |

---

## 3. REA / penetrasyon için "gözlemlenebilir yüzey" notu

Kural hatırlatması: `docs/rea/README.md` — observe-only varsayılan, kendi makinemizde
yasal edinilmiş paket, vendor'a sorumlu disclosure (90 gün). Aşağıdaki satırlar "hangi
vendor hangi test için en uygun" sorusunun **ölçülebilir cevabıdır**, davet değil.

- **Chrome for Testing — referans/otomasyon testi için en uygun.** Google'ın kendi otomasyon
  önerisi; CDP yüzeyi tam, sürüm sabit (auto-update yok), `/json/protocol` ile build'e özel
  domain şeması çıkarılabilir. Gözlemlenebilir yüzey: non-default `--user-data-dir` ile açık
  localhost port + `DevToolsActivePort` + tahmin edilemez UUID browser WS path. Tehdit
  modeli (Google'ın kendi gerekçesiyle): 136+ kısıtlaması infostealer'ların kayıtlı profil
  cookie'lerini CDP üzerinden çalmasını önlemek için — yani **CDP port'u cookie hırsızlığı
  testi için bilinen, vendor-çağrışımlı vektördür** ([embracethered cookie theft 2024](https://embracethered.com/blog/posts/2024/cookie-theft-in-2024-and-what-todo/),
  [developer.chrome.com](https://developer.chrome.com/blog/remote-debugging-port)).
- **Edge — politika/kurumsal kısıt testi için en uygun.** `RemoteDebuggingAllowed` ve
  `DeveloperToolsAvailability(+Allow/Blocklist)` politikalarının CDP'yi hedef-bazlı nasıl
  daralttığı ölçülebilir; REA'da "politika kapalıyken hangi endpoint hâlâ cevap veriyor"
  testi için tek vendor (belgelenmiş politika yüzeyi).
- **Brave — patch-lag + parmak izi tutarlılık testi için en uygun.** CDP yüzeyi stok
  olduğundan domain testi üretmez; üreten şey (a) repo'da ölçülen sürüm-tazelik farkı
  (Chromium 114 tabanlı paket), (b) farbling nedeniyle tekrarlı ziyaretler arası canvas/audio
  tutarsızlığı. CDP port'unun kimliksiz localhost davranışı 2026'da bağımsız olarak ölçülmüş
  ([pedrosatin.com](https://pedrosatin.com/en/blog/brave-remote-debugging-authorization)).
- **Opera — resmi otomasyon araç-zinciri testi için en uygun.** `opera-devtools-mcp` +
  `opera-browser-cli` vendor'ın kendi CDP tüketicisi; `DevToolsActivePort`/`SingletonLock`
  invariant'ları dokümante. Startup-only port kuralı, "açık oturuma sonradan sızma" senaryosunun
  Opera'da neden imkânsız olduğunu gösterir.
- **Vivaldi — negatif kontrol (yüzeyin kapalı olduğunu kanıtlama) için en uygun.** Üç
  bağımsız kanıt (repo bench probe'ı, flatten sapması, headless yokluğu) otomasyon
  karşıtı/eksik vendor profilini dolduruyor. REA için anlamı: Vivaldi'yi otomasyon hedefi
  listesinden çıkarmak **ölçülmüş** bir karardır; Windows/macOS'ta tekrar test edilmeden
  "tüm platformlarda kapalı" denemez (repo planı bunu zaten işaretliyor).
- **Lightpanda (opsiyonel karşılaştırma) — protokol-uyumluluk testi için ikinci referans.**
  Tam olmayan CDP implementasyonu (17 domain, render yok) hangi CDP komutlarının gerçekten
  gerekli olduğunu ayırt eden bir "asgari yüzey" testi üretir: Puppeteer temel akışları
  çalışır, Emulation/Debugger/screenshot tabanlı akışlar çalışmaz.

---

## 4. Kaynak listesi (kullanım sırası)

1. https://chromedevtools.github.io/devtools-protocol/ (domain tanımı, HTTP endpoint'leri, security/origin restrictions, `/json/protocol`)
2. https://developer.chrome.com/blog/remote-debugging-port (Chrome 136+ port kısıtlaması, CFT önerisi)
3. https://learn.microsoft.com/en-us/microsoft-edge/test-and-automation/devtools-protocol (Edge CDP = Chrome API eşdeğerliği)
4. https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/remotedebuggingallowed + .../developertoolsavailability (Edge politika yüzeyi)
5. https://github.com/brave/brave-core/pull/5500 (Brave remote debugging default proxy)
6. https://pedrosatin.com/en/blog/brave-remote-debugging-authorization (Brave/Chrome 144+ onaylı mod, ölçülmüş)
7. https://github.com/dev-newb/yes-dev (Chrome 144+ per-connection prompt, "always allow" yok)
8. https://www.npmjs.com/package/cdp-browser-mcp (Vivaldi flatten sapması — yalnız browser-level yanıt; Chrome/Edge eşdeğerliği; 2026-10-27'de doğrulandı)
9. https://forum.vivaldi.net/topic/27916 + /topic/34521 + /topic/112526 + /topic/111283 (Vivaldi port/headless/CDP-araç bug'ları)
10. https://github.com/operasoftware/opera-devtools-mcp + https://github.com/operasoftware/opera-browser-cli/blob/main/CLAUDE.md (Opera resmi CDP otomasyonu, startup-only port)
11. https://clearcotelabs.com/chrome-for-testing (CFT vs Chrome ölçülen farklar, headless-shell)
12. https://chromium.googlesource.com/chromium/src/+show/lkgr/headless/README.md (headless tarihçesi, M118 headless-shell, `--headless=old` kaldırma)
13. https://docs.bswen.com/blog/2026-03-19-lightpanda-cdp-puppeteer-playwright + https://github.com/Mathews-Tom/armory/blob/main/skills/lightpanda-browser/references/compatibility.md (Lightpanda 17 domain)
14. https://lightpanda.io/blog/posts/cdp-under-the-hood (CDP'nin hata-ayıklama için tasarımı, 650 komut/200 tip)
15. https://github.com/feder-cr/invisible_playwright/blob/main/docs/alternative-chromium-browsers-for-automation.md (fork'lar arası CDP yüzeyi aynıdır tezi + Brave farbling)
16. Repo içi: `docs/rea/brave.md`, `docs/rea/edge.md`, `docs/rea/vivaldi.md:28`, `docs/rea/opera.md`, `docs/rea/chrome-for-testing.md`, `docs/rea/positioning-synthesis.md` §2, `docs/rea/data/*.json` (vendor_endpoints), `docs/research/browser_engine_sota_2026-10.md` (Lightpanda karar notu)
