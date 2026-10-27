# REA — Tarayıcı Vendor Güvenlik Duruşu Değerlendirmesi (Ekim 2026)

**Kapsam:** Brave, Microsoft Edge, Vivaldi, Opera, Chrome for Testing (CFT).
**Amaç:** Her vendor için güvenlik disclosure/PSIRT kanalı, bug bounty kapsamı, 2025–2026
yüksek profilli olaylar ve REA ekibinin `observe-only` (yalnız gözlem) modunda kalması
için gerekçe. Bu doküman yeni fikir üretmez; yalnızca ölçülebilir/kanıtlanmış durumları
kaynak URL'leriyle kaydeder. Kurallar: `docs/rea/README.md` (90-day disclosure,
exploit yayın yok, yalnızca kendi makinemizde yasal edinilmiş materyal).

> Not: README'de HFY tüm hedefler için `dynamic-ok` onayı vermiştir (2026-10-25); ancak
> REA ekibinin bu doküman kapsamındaki operasyonu bilinçli olarak `observe-only` ile
> sınırlandırılır — gerekçeler her vendor satırında ayrıntılıdır. Sert sınırlar
> (README: exploit yayınlama yok, vendor sunucularına saldırı yok, DRM/anti-bot
> bypass yok) her onaya rağmen geçerlidir.

---

## 1. Brave

**Brave Software — HackerOne (`hackerone.com/brave`) + `security@brave.com` — Risk: orta
(patch-lag kritik; kendi kod yüzeyi dar) — Resmi REA seviyesi: `dynamic-ok`, operasyon: observe-only.**

| Alan | Bulgular (ölçülebilir) |
|---|---|
| Disclosure / PSIRT kanalı | HackerOne programı (`https://hackerone.com/brave`), şifreli rapor için `security@brave.com` (PGP talep üzerine). Brave "ciddi, geniş etkili" konular dışında CVE atamaz; disclosure kendi takdirine bağlıdır, fix içeren release sonrası ~2 hafta içinde kamuya açık disclosure yapmayı kabul ederler. Kaynak: `https://hackerone.com/brave`, `https://firebounty.com/72-brave-software` |
| Bug bounty kapsamı | Ödül aralıkları: Low $50–100 (ort. $100), Medium $100–250 (ort. $235), High $250–1,000 (ort. $1,036), Critical $1,000–10,000. Toplam ödenen >$140,000; gerçekleşen üst ödemeler $500–$5,300. Kapsam: Brave'in kendi kodu (Shields, Rewards, Wallet, Tor pencereleri, sync, GitHub `brave`/`brave-intl` repoları) + kullanıcı izni olmadan giden ağ bağlantıları (gizlilik ihlali sınıfı). Chromium'dan miras hatalar genelde kapsam dışı (Chromium ekibine). 2025-11-26'da LLM/AI Agent güvenlik sınıfı eklendi (prompt injection, kanıtlanabilir veri sızıntısı şartıyla). DoS/crash kapsam dışı. Kaynak: `https://hackerone.com/brave` |
| Son yüksek profilli olaylar (2025–2026) | (a) **CVE-2025-48980** (NVD 2025-10-31): Split View "Open Link in Split View" menüsü `SameSite=Strict` cookie'lerini cross-site navigasyonda gönderiyor — CSRF koruması bypass, düzeltme 1.83.10, disclosure kaydı HackerOne rapor #3253725. Kaynak: `https://sentinelone.com/vulnerability-database/cve-2025-48980`, `https://hackerone.com/reports/3253725`. (b) **CVE-2025-23086** (2025-01): 1.70.x–1.73.x dosya seçici diyalogda origin gösterimi spoofing (open redirector zinciri). Kaynak: `https://valtersit.com/cve/CVE-2025-23086`. (c) **CVE-2025-5419** (Chromium V8, in-the-wild): Brave 1.79.119 altında etkilendi, yama zorunlu. Kaynak: `https://lis.mcut.edu.tw/p/404-1013-73337.php?Lang=en`, `https://helpnetsecurity.com/2025/06/04/google-fixes-chrome-zero-day-with-in-the-wild-exploit-cve-2025-5419`. (d) **CVE-2026-5272…CVE-2026-5292** (21 yüksek riskli Chromium açığı, içlerinde **CVE-2026-5281** in-the-wild): Brave 1.88.138 altında etkilendi. Kaynak: `https://lis.mcut.edu.tw/p/404-1013-77946.php?Lang=en`. (e) **Repo içi ölçümlü bulgu (2026-10-25 CDP probe):** apt deposundaki en yeni Brave stable'ı Chromium 114 tabanlı — CFT'ye göre **42 major geride** (bkz. `docs/rea/README.md` cross-target tablosu); tek başına en büyük patch-lag. |
| Observe-only gerekçesi | (1) HackerOne kapsam kuralları yalnızca kendi hesabınızla etkileşimi ve normal oturum trafiğini izin verir; aktif test/fuzzing kapsam dışına ve programa zarar verebilir. (2) Brave'in ödüllü yüzeyi kendi kodudur; Chromium miras hataları kapsam dışı olduğundan exploit geliştirme çabası karşılıksız ve hatalı kanaldır. (3) CVE-2025-48980 gibi bulgular disclosure kanalının (HackerOne) çalıştığını gösterir — bulgu çıkarsa raporlama yolu nettir, aktif istismar gerekmez. (4) Patch-lag (42 major) zaten pasif sürüm/UA ölçümüyle kanıtlandı; daha fazlası için dinamik sömürü gerekmez. |

## 2. Microsoft Edge (Chromium tabanlı)

**Microsoft — MSRC (Microsoft Security Response Center), `https://msrc.microsoft.com/report/vulnerability` — Risk: orta (Chromium yama takibi düzenli, vendor-specific CVE'ler var) — Resmi REA seviyesi: `dynamic-ok`, operasyon: observe-only.**

| Alan | Bulgular (ölçülebilir) |
|---|---|
| Disclosure / PSIRT kanalı | MSRC Researcher Portal (`https://msrc.microsoft.com/report/vulnerability`); MSRC Coordinated Vulnerability Disclosure (CVD) politikası ve "Microsoft Bounty Legal Safe Harbor" kapsamında iyi niyetli araştırmaya açık güvenli liman tanımı vardır. Edge güvenlik düzeltmeleri `https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnotes-security` üzerinde periyodik yayınlanır. Kaynak: `https://microsoft.com/en-us/msrc/bounty-programs`, `https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnotes-security` |
| Bug bounty kapsamı | Microsoft Edge Bounty Programı: $100–$30,000 USD (Microsoft takdirine bağlı olarak daha yüksek olabilir). Yüksek etki senaryoları: Sandbox Escape (Critical/Important tam rapor) $30,000; bilgi sızıntısı / güvenlik özelliği bypass (tam rapor) $20,000; renderer RCE $10,000; spoofing/tampering $7,500. Kriter: Chromium tabanlı Edge'e özgü, Chrome'da üretilmeyen, son sürümde + son yamalı OS'te tekrarlanabilir, PoC zorunlu. WebView2 SDK/runtime dahil. DoS kapsam dışı. 2025-12-11'de "In Scope by Default" ile kritik online servis varsayılan kapsama alındı. Copilot Mode AI hataları ayrı Copilot Bounty Programı'na (2025-10-28 eklendi). Kaynak: `https://microsoft.com/en-us/msrc/bounty-new-edge`, `https://microsoft.com/en-us/msrc/blog/2025/12/in-scope-by-default` |
| Son yüksek profilli olaylar (2025–2026) | (a) **CVE-2025-5419** (V8 heap bozulması, in-the-wild): Edge Stable 2025-06-03 yaması ile düzeltildi. Kaynak: `https://helpnetsecurity.com/2025/06/04/google-fixes-chrome-zero-day-with-in-the-wild-exploit-cve-2025-5419` (Edge yama referansı: `https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnotes-security#june-3-2025`). (b) **CVE-2026-5272** (Chromium GPU heap buffer overflow, High): Edge 146.0.3856.97 (2026-04-02) ile kapandı; Chromium 146.0.7680.178 tabanlı. Kaynak: `https://exploitdog.ru/cve/msrc/CVE-2026-5272`, `https://rapid7.com/db/vulnerabilities/microsoft-edge-cve-2026-5272`. (c) **CVE-2026-5281** (in-the-wild, aynı 21'lık Chromium paketi): Edge < 146.0.3856.97 etkilendi. Kaynak: `https://lis.mcut.edu.tw/p/404-1013-77946.php?Lang=en`. (d) **CVE-2026-72970** — Edge'e özgü güvenlik düzeltmesi, 2026-08-14 ve 2026-10-16 sürümlerinde tekrar işlendi. Kaynak: `https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnotes-security`. |
| Observe-only gerekçesi | (1) MSRC Bounty kuralları/Rules of Engagement yalnızca iyi niyetli, kendi kontrolünüzdeki ortamda testi güvenli limana dahil eder; bunun dışındaki dinamik istismar CFAA/AB hukuku riski taşır. (2) Edge'e özgü açık bulmak, Chrome'da üretilmeyen bir etki kanıtı gerektirir — bu, aktif exploit zinciri kurmadan yapılamaz; REA'nın "exploit yok" kuralı bunu dışlar. (3) Chromium miras açıkları zaten Google VRP kanalıyla raporlanır; MSRC bunları yalnızca yama duyurusu için belgeler. (4) Vendor-specific CVE'ler (CVE-2026-72970) düzenli yayın notlarından pasif olarak izlenebilir. |

## 3. Vivaldi

**Vivaldi Technologies — Vivaldi Security Group, `https://vivaldi.com/bugreport/` (gizli rapor) — Risk: orta-yüksek (küçük ekip, 4 major patch-lag, ücretli bounty yok) — Resmi REA seviyesi: `dynamic-ok`, operasyon: observe-only.**

| Alan | Bulgular (ölçülebilir) |
|---|---|
| Disclosure / PSIRT kanalı | Vivaldi Security Group; gizli rapor için `https://vivaldi.com/bugreport/` (forum/sosyal medya üzerinden raporlama istenmiyor). Responsible disclosure: sorun stable düzeltmesi yayınlanana kadar araştırma açıklanmaz; disclosure tarihi vaka bazında kararlaştırılır. Güvenlik derecelendirme politikası: `https://vivaldi.com/security/how-we-rate-security-issues`. Kaynak: `https://vivaldi.com/security` |
| Bug bounty kapsamı | **Ücretli bug bounty yok.** Karşılığı: Hall of Fame'de yazılı kredi (`https://vivaldi.com/security/hall-of-fame`); 2025–2026 listesinde az sayıda araştırmacı (ör. 2026'da "crnkovic" web/servis critical, "Mahender Singh" ürün high). Doğrulanmış üçüncü taraf değerlendirmesi: "no paid bug-bounty program — only coordinated disclosure with a Hall of Fame credit". Kaynak: `https://vivaldi.com/security`, `https://vivaldi.com/blog/an-insight-into-security-research-and-ethical-hacking`, `https://privacypick.com/browsers/vivaldi` |
| Son yüksek profilli olaylar (2025–2026) | (a) **CVE-2025-5419** (Chromium heap overflow, in-the-wild): Vivaldi < 7.4.3684.50 etkilendi. Kaynak: `https://lis.mcut.edu.tw/p/404-1013-73337.php?Lang=en`. (b) **CVE-2026-5272…5292** (21 yüksek riskli Chromium açığı, CVE-2026-5281 in-the-wild): Vivaldi < 7.9.3970.47 etkilendi. Kaynak: `https://lis.mcut.edu.tw/p/404-1013-77946.php?Lang=en`. (c) **Repo içi ölçümlü bulgu (2026-10-25):** Vivaldi 8.2.4133.94-1 → Chromium 152 tabanı, CFT'ye göre 4 major geride; `update-ffmpeg` + apt güncelleme mekanizması (bkz. `docs/rea/README.md`). (d) Vivaldi'nin gömülü üçüncü taraf uçları (`go.mail.ru`/`suggests.go.mail.ru` — `docs/rea/data/vivaldi.json` `vendor_endpoints`) yayınlanmış, ölçülebilir bir saldırı yüzeyi/catdak genişlemesidir; Hall of Fame'e göre 2025'te bir ürün açığı ve bir web/servis critical açığı raporlandı. Kaynak: `https://vivaldi.com/security/hall-of-fame` |
| Observe-only gerekçesi | (1) Ücretli bounty yok + disclosure vaka bazında ve "fix yayınlanana kadar açıklama" şartlıdır — aktif araştırma teşvik edilmez, kötüye kullanım riski ödülle dengelenmez. (2) Küçük ekip/yavaş patch döngüsü (4 major lag) nedeniyle, aktif bulgular kullanıcıları daha uzun süre açıkta bırakır; observe-only bu pencereyi genişletmez. (3) Gömülü üçüncü taraf uçları (`go.mail.ru`) sözleşme/ToS kapsamına girebilir; README kuralı: "EULA/ToS tersine mühendisliği yasaklayabilir — şüphede observe, don't decompile". (4) CVE-2025-5419 ve CVE-2026-5281 kanıtıyla asıl risk zaten upstream Chromium'dadır; fork'a özel exploit aramaya gerek yoktur. |

## 4. Opera

**Opera — Opera Security Team, `security.opera.com` + Bugcrowd (`https://bugcrowd.com/opera`) — Risk: orta (2026'da gerçek istismar yüzeyi olayı, CNA üyeliği disiplinli disclosure sağlıyor) — Resmi REA seviyesi: `dynamic-ok`, operasyon: observe-only.**

| Alan | Bulgular (ölçülebilir) |
|---|---|
| Disclosure / PSIRT kanalı | Opera Security Team: `https://security.opera.com/en/report-security-issue` (kapsam dışı raporlar için Atlassian portal formu), bug bounty `https://security.opera.com/en/bug-bounty` → Bugcrowd. **MITRE CNA üyesi (Aralık 2019'dan beri)** — uygun bulgulara CVE atayabilir. Chromium'dan miras hatalar Chromium kanalına raporlanmalıdır. Kaynak: `https://security.opera.com/en/bug-bounty`, `https://security.opera.com/en/report-security-issue` |
| Bug bounty kapsamı | Halka açık Bugcrowd programı (`https://bugcrowd.com/opera`, 2021-03-25'ten beri açık; doğrulanmış 390+ ödül; 3 aylık ort. ödeme $389.70). Ödül mantığı etki bazlı: üretilen veri sızıntısı/önemli güvenlik gereksinimi kırma $2,000–$10,000 (ana hedeflerde P1 $3,000–5,000, P2 $500–3,000, P3 $200–500, P4 $100–200; tarihsel üst sınır $10K). "Önemli güvenlik gereksinimi" örnekleri: 0-click tarama geçmişi sızıntısı, native code execution, memory corruption, SSL doğrulama bypass, JS injection. DoS/brute-force/open redirect (etkisiz) kapsam dışı. Android uygulamaları Google Play Security Rewards (GPSRP) kapsamına da girebilir. Kaynak: `https://bugcrowd.com/engagements/opera`, `https://bugrater.com/programs/opera`, `https://blogs.opera.com/security/2021/04/earn-up-to-10k-from-the-opera-bug-bounty-program` |
| Son yüksek profilli olaylar (2025–2026) | (a) **Opera GX Mods otomatik kurulum açığı (Temmuz 2026):** zhero_ ve inzo_ (Bugcrowd üzerinden, Opera'nın bug bounty programı) kötü amaçlı bir sitenin onaysız mod kurup "universal CSS injection" ile oturum açmış kullanıcının Gmail adresini tek ziyarette sızdırdığını gösterdi; Opera P1 olarak derecelendirdi ve **$5,000** (critical tavanı) ödedi. Düzeltme Opera GX 130.0.5847.89; **CVE atanmadı**; Opera sahada istismar kanıtı bulunmadığını bildirdi. Aynı otomatik kurulum yolunun gizli sekmede .crx ile tarayıcıyı çökerttiği ayrıca belgelendi (Opera ana sürümünü de etkiler). Kaynak: `https://blogs.opera.com/security/2026/07/security-fix-gx-mods-vulnerability`, `https://thehackernews.com/2026/07/opera-gx-flaw-let-malicious-sites-auto.html`. (b) **CVE-2025-5419** (in-the-wild Chromium): Opera < 119.0.5497.70 etkilendi. Kaynak: `https://lis.mcut.edu.tw/p/404-1013-73337.php?Lang=en`. (c) **CVE-2026-5272…5292** (CVE-2026-5281 in-the-wild): Opera < 129.0.5823.65 etkilendi. Kaynak: `https://lis.mcut.edu.tw/p/404-1013-77946.php?Lang=en`. (d) **Repo içi ölçümlü bulgu (2026-10-25):** Opera 138.0.6044.24 → Chromium 154, CFT'ye göre 2 major geride; bağımsız `opera_autoupdate` 1.3.0 mekanizması; gömülü `go.mail.ru`/`cashback.opera.com` uçları (bkz. `docs/rea/README.md`, `docs/rea/data/`). |
| Observe-only gerekçesi | (1) GX Mods olayı, mod/extension kurulum pipeline'ının gerçek, ödüllü bir istismar yüzeyi olduğunu kanıtladı — bu yüzeyde aktif deneme, "mod indirme/etkinleştirme" trafiğiyle vendor scope'unu ve sert sınır "normal oturum dışında trafik üretme" kuralını ihlal eder. (2) Bugcrowd kuralları: Chromium miras hataları Chromium'a, 3. parti hatalar 3. parti vendora gider; Opera'ya özel exploit kanıtı gereklidir — REA'nın "exploit yok" kuralıyla bağdaşmaz. (3) CNA üyeliği ve $5,000 P1 ödemesi, kanalın çalıştığını gösterir — bulgu çıkarsa raporlama yolu (Bugcrowd) nettir. (4) Gömülü üçüncü taraf uçları pasif olarak `docs/rea/data/*.json` üzerinden izlenebilir; aktif temas gerekmez. |

## 5. Chrome for Testing (CFT)

**Google (Chrome takımı) — ayrı PSIRT yok; Chrome Releases blog + Chrome VRP (`https://g.co/chrome/vrp`, `https://bughunters.google.com`) — Risk: düşük-orta (sabit sürüm, otomatik güncelleme yok → yönetilen patch gerekir) — Resmi REA seviyesi: `dynamic-ok`, operasyon: observe-only.**

| Alan | Bulgular (ölçülebilir) |
|---|---|
| Disclosure / PSIRT kanalı | CFT, Chrome'un bir sürüm lezzetidir — kendi PSIRT'u yoktur. Güvenlik bildirimleri Chrome Releases blogunda yayınlanır (`https://chromereleases.googleblog.com`); raporlama Chrome VRP / Google Bug Hunters üzerinden yapılır (`https://bughunters.google.com/about/rules/chrome-friends`). Chromium dokümanı: `https://chromium.googlesource.com/chromium/src/+/main/docs/chrome_for_testing`, `https://developer.chrome.com/docs/automation-and-testing/chrome-for-testing` |
| Bug bounty kapsamı | Chrome VRP (2025 itibarıyla yeniden yapılandırıldı): memory corruption taban ödül $2,000 (4x artış); browser/network/GPU süreçleri $4,000–$20,000 (controlled write $20,000); renderer $3,000–$8,000; V8 sandbox $5,000, V8 mantık $4,000; non-memory-safety sandbox escape **$20,000'e kadar**; S2 (medium) düzeltmeleri $2,000; fuzzer bonusu $2,000. **Tek rapor için en yüksek ödül $250,000** (non-sandboxed süreçte kanıtlanmış RCE); MiraclePtr bypass bonusu $250,128. Gerçekleşen rekor ödeme: **CVE-2025-4609 için $250,000**. Kaynak: `https://bughunters.google.com/blog/changes-to-the-chrome-vrp-restructuring-rewards`, `https://bleepingcomputer.com/news/google/google-increases-chrome-bug-bounty-rewards-up-to-250-000`, `https://securityonline.info/record-breaking-payout-google-awards-250000-for-a-critical-chrome-flaw-cve-2025-4609`, `https://bughunters.google.com/blog/evolving-the-android-chrome-vrps-for-the-ai-era` |
| Son yüksek profilli olaylar (2025–2026) | (a) **CVE-2025-2783** (Mart 2025): sandbox escape, Rus devlet destekli grupça casusluk saldırılarında kullanıldı (Kaspersky yakaladı). Kaynak: `https://securityweek.com/google-researchers-find-new-chrome-zero-day` (iç referans), `https://securityweek.com/google-patches-chrome-sandbox-escape-zero-day-caught-by-kaspersky/`. (b) **CVE-2025-5419** (Haziran 2025): V8 out-of-bounds read/write, in-the-wild; TAG araştırmacıları (Lecigne, Sevens) bildirdi; yama 137.0.7151.68/.69; detaylar kullanıcıların çoğunluğu yamalayana dek kısıtlandı. Kaynak: `https://chromereleases.googleblog.com/2025/06/stable-channel-update-for-desktop.html`, `https://securityweek.com/google-researchers-find-new-chrome-zero-day`, `https://helpnetsecurity.com/2025/06/04/google-fixes-chrome-zero-day-with-in-the-wild-exploit-cve-2025-5419`. (c) **CVE-2025-4609**: VRP tavanı $250,000 ödendi (program rekoru). Kaynak: `https://securityonline.info/record-breaking-payout-google-awards-250000-for-a-critical-chrome-flaw-cve-2025-4609`. (d) **CVE-2026-5272…CVE-2026-5292** (Nisan 2026, 21 yüksek riskli açık; **CVE-2026-5281 in-the-wild**): Chrome < 146.0.7680.177 etkilendi. Kaynak: `https://lis.mcut.edu.tw/p/404-1013-77946.php?Lang=en`. (e) Haziran 2026'da ayrı bir Chrome zero-day (**CVE-2026-11645**) raporlandı (aynı olay değildir). Kaynak: `https://laptop251.com/google-patches-chrome-zero-day-exploited-in-attacks-update-now`. (f) **CFT'ye özgü yapısal risk (ölçülebilir):** CFT otomatik güncelleme içermez ve bileşen güncellemeleri varsayılan olarak kapalıdır (`kComponentUpdatesEnabledByDefault=false`); sürüm pinli kalır — patch uygulamak operatör sorumluluğudur. Kaynak: `https://chromium.googlesource.com/chromium/src/+/main/docs/chrome_for_testing`, `https://developer.chrome.com/docs/automation-and-testing/chrome-for-testing` |
| Observe-only gerekçesi | (1) CFT açıkça otomasyon/test için yayınlanmış bir binary'dir; yasal edinim ve statik/dinamik inceleme README kapsamında en rahat burada yapılabilir — ancak bulgu sınıfı Chrome VRP'ye aittir ve VRP kuralları kanıtlanmış etki (PoC, kontrollü okuma/yazma) ister; bu REA'nın "exploit yok" kuralıyla doğrudan çelişir. Bu yüzden REA yalnızca sürüm/UA/CDP ölçümü ve pasif trafik gözlemi yapar, VRP'ye raporlanacak bir bulgu çıkarsa minimal kanıt hazırlığı ayrıca onaylanır. (2) In-the-wild olayların (CVE-2025-2783, CVE-2025-5419, CVE-2026-5281) tamamı upstream Chromium/V8 yüzeyindedir; Chrome Releases + NVD takibi pasif olarak yeterlidir. (3) Sabit sürüm + kapalı bileşen güncellemesi nedeniyle REA test ortamı bilinçli olarak pinli kalmalı, fakat bu pin exploit için değil, tekrarlanabilir ölçüm içindir. |

---

## REA ekibi için eylem listesi (observe-only)

### Yapılabilir (izinli — README "What is allowed" ile uyumlu)

- [x] Kendi makinemizde, kendi trafiğimizin **pasif** gözlemi (temiz test profili, kendi hesabımız) — `docs/rea/data/idle_network.json` benzeri endpoint haritalama.
- [x] Sürüm/UA/V8/Chromium taban ölçümü (headless CDP `/json/version` gibi, sunucuya yük bindirmeyen, yerel sorgular) — patch-lag tablosu bu yöntemle üretildi.
- [x] Statik inceleme: paket açma, manifest/bileşen envanteri (`docs/rea/data/*.json` içindeki `bundled_extensions`, `vendor_endpoints`).
- [x] Genel doküman/changelog/advisory/CVE okuma ve vendor güvenlik sayfalarının izlenmesi (URL'ler yukarıda).
- [x] Bulgu çıkarsa: README disclosure adımları — vendor'ın resmi kanalına özel rapor (Brave: HackerOne/security@brave.com; Edge: MSRC portal; Vivaldi: bugreport formu; Opera: Bugcrowd; Chrome: VRP), sürüm+hash, kendi makinemizde minimal reprodüksiyon, etki değerlendirmesi; `docs/rea/<target>.md` içine "reported: date, channel, case id" kaydı.
- [x] 90-day disclosure penceresi (makul vendor talebiyle bir kez uzatılabilir); yayın yalnızca fix veya süre sonunda, nötr dilde.

### Yapılamaz (sert sınır — README "What is NOT allowed" ile uyumlu)

- [x] Exploit geliştirme, weaponize etme, yayınlama; kavram kanıtı bile olsa "minimal proof" ötesine geçme (yalnız kendi makinemizde ve ayrıca onaylıysa).
- [x] Vendor sunucularına karşı fuzzing, yük testi, tarama; normal oturum trafiğini aşan herhangi bir etkileşim (Opera mod kurulum hattı, Brave Rewards uçları vb. dahil).
- [x] DRM/lisans kontrolü kırma, paywall/entitlement bypass, anti-bot/fraud-detection aşma.
- [x] Vendor kaynak kodu, proprietary blob, özel anahtar yayınlama (statik incelemede bulunanlar dahil).
- [x] Diğer kullanıcıların verisi/hesabı üzerinde test; sahte/ele geçirilmiş hesap kullanımı.
- [x] EULA/ToS ile çelişen aktif tersine mühendislik — şüphede "observe, don't decompile" (Vivaldi/Opera üçüncü taraf gömülü bileşenleri için özellikle geçerli).
- [x] Bulgu çıkmadan kamuya açık issue/duyuru; disclosure yalnızca vendor'ın resmi kanalına özel yapılır.

---

## Kaynak URL indeksi

| # | Kaynak | Kullanıldığı yer |
|---|---|---|
| 1 | https://hackerone.com/brave | Brave disclosure + bounty |
| 2 | https://firebounty.com/72-brave-software | Brave bounty tarifesi + disclosure |
| 3 | https://security@brave.com (e-posta kanalı; PGP talep üzerine) | Brave şifreli rapor |
| 4 | https://sentinelone.com/vulnerability-database/cve-2025-48980 | CVE-2025-48980 |
| 5 | https://hackerone.com/reports/3253725 | CVE-2025-48980 disclosure kaydı |
| 6 | https://valtersit.com/cve/CVE-2025-23086 | CVE-2025-23086 |
| 7 | https://microsoft.com/en-us/msrc/bounty-new-edge | Edge bounty ($100–$30,000) |
| 8 | https://microsoft.com/en-us/msrc/bounty-programs | MSRC program listesi + CVD |
| 9 | https://microsoft.com/en-us/msrc/blog/2025/12/in-scope-by-default | MSRC "In Scope by Default" |
| 10 | https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnotes-security | Edge güvenlik bültenleri (CVE-2026-72970, yama sürümleri) |
| 11 | https://vivaldi.com/security | Vivaldi Security Group + disclosure |
| 12 | https://vivaldi.com/security/hall-of-fame | Vivaldi Hall of Fame (bounty yok) |
| 13 | https://vivaldi.com/blog/an-insight-into-security-research-and-ethical-hacking | Vivaldi ödül modeli (kredi) |
| 14 | https://privacypick.com/browsers/vivaldi | Vivaldi: ücretli bounty yok teyidi |
| 15 | https://security.opera.com/en/bug-bounty | Opera Bugcrowd + CNA üyeliği |
| 16 | https://security.opera.com/en/report-security-issue | Opera rapor kanalları |
| 17 | https://bugcrowd.com/engagements/opera | Opera bounty aralıkları |
| 18 | https://bugrater.com/programs/opera | Opera ödül mantığı |
| 19 | https://blogs.opera.com/security/2026/07/security-fix-gx-mods-vulnerability | Opera GX Mods olayı (resmi advisory) |
| 20 | https://thehackernews.com/2026/07/opera-gx-flaw-let-malicious-sites-auto.html | Opera GX olayı ($5,000 ödeme, no CVE) |
| 21 | https://bughunters.google.com/blog/changes-to-the-chrome-vrp-restructuring-rewards | Chrome VRP yeniden yapılandırma |
| 22 | https://bleepingcomputer.com/news/google/google-increases-chrome-bug-bounty-rewards-up-to-250-000 | Chrome VRP $250,000 tavanı |
| 23 | https://securityonline.info/record-breaking-payout-google-awards-250000-for-a-critical-chrome-flaw-cve-2025-4609 | CVE-2025-4609 $250K ödeme |
| 24 | https://bughunters.google.com/blog/evolving-the-android-chrome-vrps-for-the-ai-era | Chrome VRP 2026 güncellemesi |
| 25 | https://chromereleases.googleblog.com/2025/06/stable-channel-update-for-desktop.html | CVE-2025-5419 resmi bülten |
| 26 | https://securityweek.com/google-researchers-find-new-chrome-zero-day | CVE-2025-5419 + CVE-2025-2783 bağlamı |
| 27 | https://helpnetsecurity.com/2025/06/04/google-fixes-chrome-zero-day-with-in-the-wild-exploit-cve-2025-5419 | CVE-2025-5419, Edge yaması |
| 28 | https://lis.mcut.edu.tw/p/404-1013-73337.php?Lang=en | CVE-2025-5419 tüm fork'lar (Brave 1.79.119, Vivaldi 7.4.3684.50, Opera 119.0.5497.70) |
| 29 | https://lis.mcut.edu.tw/p/404-1013-77946.php?Lang=en | CVE-2026-5272…5292, CVE-2026-5281 in-the-wild |
| 30 | https://exploitdog.ru/cve/msrc/CVE-2026-5272 | CVE-2026-5272 Edge yaması (146.0.3856.97) |
| 31 | https://chromium.googlesource.com/chromium/src/+/main/docs/chrome_for_testing | CFT yapısal farkları (bileşen güncelleme kapalı) |
| 32 | https://developer.chrome.com/docs/automation-and-testing/chrome-for-testing | CFT tanımı (otomatik güncelleme yok) |
| 33 | https://laptop251.com/google-patches-chrome-zero-day-exploited-in-attacks-update-now | CVE-2026-11645 (Haziran 2026) ayrımı |

*Bu doküman yalnızca kaynaklı, ölçülebilir durumları kaydeder; hukuki tavsiye değildir
(README "Legal basis" notu geçerlidir). REA operasyon kuralları için bkz. `docs/rea/README.md`.*
