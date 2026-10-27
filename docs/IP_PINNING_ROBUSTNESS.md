# IP Pinning / DNS Rebinding'e Karşı Sertleştirme

## Genel Mimari / Neden Bu Konu?

Ağ dışına açılan her bağlantı noktası (`BrowserWorker` üzerinden `urllib` tabanlı HTTP sürücüsü,
adapter doğrulama istekleri, robot.txt kontrolleri) DNS çözünürlüğü ile bağlantı kurma arasında
zaman tabanlı bir tutarsızlık (TOCTOU) riski taşır.

* Bir alan adı (`attacker.test`) başta güvenli bir IP'ye (`203.0.113.10`) çözümlenebilir.
* `EgressPolicy` bu IP'yi `public` olarak onaylar.
* Ancak `urlopen` (ve birçok HTTP istemcisi) **çözümleme ve soket açma arasında** DNS
  kaydını yeniden çözebilir. Saldırgan bu pencerede DNS cevabını `127.0.0.1` /
  `169.254.169.254` gibi iç bir adrese çevirirse, bağlantı IP'si "onaylı" olsa bile
  fiilen iç servislere ulaşır (DNS Rebinding / SSRF).
* Ayrıca `urllib`'in takip ettiği `30x` yönlendirmeleri `Location` başlığındaki yeni
  hedefi **egress kontrolünden geçirmeden** açar; kuraldışı bir yönlendirme zinciriyle
  iç ağ hedeflerine sızılabilir.

Hedef: Bir işin (veya tekil bir HTTP çağrısının) başladığı andaki DNS cevabı ile gerçekten
bağlantı kurulan IP'nin **farklı olmasını teknik olarak imkânsız kılmak** (veya reddetmek).

## Mevcut Kod Akışı

1. `worker.py::BrowserWorker.execute_task` içindeki `_default_url_raw` / `_default_url_driver`,
   `adapter_registry` doğrulama fetchleri ve `_allowed_by_robots` (robots.txt fetchi) doğrudan
   `urllib.request.urlopen` kullanıyordu (her çağrıda kendi çözümlemesiyle).
2. `egress_guard.py::EgressPolicy.check_url` yalnızca **çağrı anındaki** DNS kaydını alıp
   `egress_proxy.py` içindeki `check_ip` ile test ediyor; onay sonrası `urlopen` ikinci kez
   çözümleme yapıyordu.
3. `server.py` içindeki `_guarded_driver` yalnızca `EgressPolicy`'yi enjekte ediyordu.
4. `_pinned_fetch` dikişi mevcuttu fakat geçici bir `functools.partial` yamasıyla
   `urlopen`'a sadece IP literal adresi enjekte ediyordu.

## Yeni Tasarım

### 1. `egress_proxy.py` — `pinned_opener` + `_PinnedHTTPConnection` / `_PinnedHTTPSConnection`

* `EgressPolicy.check_url` sonucunda dönen `Egress` nesnesi artık **doğrulanmış IP** (`egress.ip`)
  ile birlikte saklanıyor.
* `_PinnedHTTPConnection(host, pinned_ip)`: `connect()` içinde `socket.create_connection`
  çağrısı doğrudan `(pinned_ip, port)` üzerinden yapılıyor; `host` yalnızca `Host` başlığı ve
  TLS SNI/`server_hostname` için korunuyor.
* `_PinnedHTTPSConnection`: TLS `wrap_socket` çağrısı `server_hostname=self.host` ile yapılıyor;
  yani sertifika doğrulaması alan adına karşı (SAN/CN) sürüyor, bağlantı ise sabit IP'ye gidiyor.
  (Zayıf `check_hostname`'in sebep olduğu `ValueError` yutma riski kapatıldı; test edildi.)
* `pinned_opener(pinned_ip)`: `OpenerDirector` **redirect handler'sız** kurulur — `302` vb.
  cevaplar `HTTPError` olarak yukarı taşınır; `_pinned_fetch` her yönlendirme hedefini
  taze DNS + taze egress politikasıyla yeniden doğrular.

### 2. `worker.py` — `_pinned_fetch` ve `_check_hop` (PIN + RE-VALIDATE)

* Her çağrı (robots.txt fetchi dahil) **bir kez** `check_url` ile çözümlenir; elde edilen
  `Egress.ip` bağlama anında zorlanır (`pinned_opener`).
* `30x` yönlendirmeleri zinciri: yeni `Location` hedefi `urllib.parse.urljoin` ile birleştirilir
  ve **yeniden** `check_url`'dan geçirilir (`max_hops=10`). Onaysız hedef `FetchBlocked` /
  `EgressDenied` ile düşer.
* `_allowed_by_robots` fetchi de aynı pinned-IP yolundan geçer (aynı origin için pin yeniden
  kullanılır; ek DNS çözümlemesi yapılmaz).
* `server.py::_guarded_driver` her istek için `private_targets_allowed(allow_private)` kapsamını
  ContextVar üzerinden yönetir; `execute_task` içindeki `user_directed` bayrağı artık yalnızca
  kendi çağrısına yayılıyor (sızarsa sonraki otomatik fetchler robots'u atlar — politika bypass).

### 3. Sınırlar / Kapsam Dışı

* WebSocket, QUIC, `ftp://`, `data:` şemaları yine açık URL kabul edilmiyor.
* Script içindeki yan etkili ağ çağrıları (JS `fetch`, `WebRTC`, `navigator.sendBeacon`)
  işletim sistemi / tarayıcı ağ katmanına bağlıdır; kapsam dışıdır.

## Test / Doğrulama (Dinamik - Canlı)

Yeni test dosyası: `tests/test_ip_pinning.py` (her test kendi loopback HTTP sunucusunu kurar;
gerçek dış ağ trafiği yoktur).

| Test | Kontrol ettiği güvenlik özelliği |
|---|---|
| `test_opener_dials_ip_and_never_resolves_hostname` | Hostname'i hiç çözümlemeden yalnızca doğrulanmış IP'ye bağlanır; 3xx yönlendirme `HTTPError` olarak caller'a döner. |
| `test_fetch_pins_to_validated_ip_single_resolution` | `_default_url_raw` çözümlemeyi yalnızca bir kez yapar, bağlantıyı o IP'ye kurar (DNS rebinding penceresi kapalı). |
| `test_strict_policy_denies_private_target_before_connect` | `http://127.0.0.1/...` literal hedef, politika açılmadan `FetchBlocked` (SSRF kapanır). |
| `test_non_http_schemes_are_blocked` | `ftp://`, `data://`, `file://`, `javascript:` şemaları çözümleme/erişim öncesi reddedilir (ölçümle doğrulandı). |
| `test_redirect_to_denied_host_is_blocked_and_not_fetched` | `302` ile başka host'a yönlendirme, bağlantı açılmadan yeniden politika kontrolünden geçer; yasaklıysa `FetchBlocked`. |

Ek (aynı turda bulunan): `tests/test_user_directed_robots.py::test_user_directed_flag_does_not_leak_beyond_execute_task`
— `user_directed=True` bayrağı çağrı sonrası ContextVar'dan sıfırlanmazsa sonraki otomatik
fetchler robots.txt'i atlayabilirdi; artık kapsam çağrıyla sınırlı.

### Durum (doğrulandı)

* RED turu: `tests.test_ip_pinning` 4/4 hata (eski `urlopen` yaması ile pencere açık).
* GREEN turu: `tests.test_ip_pinning` 5/5 yeşil + `test_non_http_schemes_are_blocked` (2026-10-27 eklendi) + sızıntı testi yeşil.
* Tam süit: `python -m unittest discover -s tests -t .` → **604 test OK** (5 skip; canlı/geçici).
* Regresyonlar: `test_bench_fidelity` fixture harness'i bilerek `private_targets_allowed(True)`
  ile localhost'a koşuyor (CI içi deterministik bench); `test_http_driver` /
  `test_user_directed_robots` / `test_robots_ttl` / `test_refusal_classification` politika
  dikişlerine göre güncellendi (`EgressPolicy(allow_literal=True)`).

## Yeni Korunan Yüzeyler / Kapsam Matrisi

| Vektör | Eski | Yeni |
|---|---|---|
| `https://trusted.example` → A kaydı `203.0.113.10` → kayıt aniden `127.0.0.1` | `urlopen` soket açarken `127.0.0.1`'e gidebilirdi | `_pinned_fetch` yalnızca onaylı `203.0.113.10`'a bağlanır |
| `302 Location: http://169.254.169.254/` | Yeni hedef politikasız açılır | Yeniden politika kontrolü; `EgressDenied`/`FetchBlocked` |
| `ftp://`, `data:`, `file://`, `javascript:` URL'leri | Ölçüldü: `FetchBlocked` ("scheme not allowed") ile reddediliyor | Ölçümle doğrulandı (bkz. `test_non_http_schemes_are_blocked`) |
| Çoklu yönlendirme (`302 -> 302 -> ...`) | Zincir sonu politikasız | Her hedefte `check_url` (kayıt IP'si + pin) |
| TLS SNI / sertifika eşleşmesi | Yanlış host'a sertifika doğrulaması riski | `_PinnedHTTPSConnection` `server_hostname=self.host` |
| `robots.txt` fetchi | Her zaman serbest ağ | Aynı pin + politika; TTL penceresinde tek çözümleme |
| `user_directed` bayrağı | Sonsuza kadar açık kalabilirdi (ContextVar sızıntısı) | Çağrı sonunda `reset` |

## Canlı TLS Doğrulaması (2026-10-27)

Mock değil; gerçek kendinden-imzalı sertifika (SAN `DNS:localhost` + `IP:127.0.0.1`) + loopback HTTPS sunucusu ile gerçek TLS el sıkışmaları ölçüldü. Kod değiştirilmedi.

| Senaryo | Sonuç |
|---|---|
| Worker yolu (`_default_url_raw`), default trust, self-signed sertifika | `URLError(SSLCertVerificationError)`, verify_code=18, "certificate verify failed: self-signed certificate" |
| Aynı çağrı, sertifika trust store'a anchor edildiğinde | **SUCCESS**, gövde `tls-pinned-ok` → reddin tek nedeni sertifika zinciri doğrulaması |
| `_PinnedHTTPSConnection` doğrudan, CERT_NONE, gerçek handshake (TLSv1.3) | **SUCCESS**; `server_hostname='localhost'` (=URL host), dialed IP `127.0.0.1` (=pin'li IP) |
| URL host `wrong.test` (SAN'da yok) | `SSLCertVerificationError`, verify_code=62, "Hostname mismatch" — `ValueError` değil |
| IP-literal URL (`127.0.0.1`) | **SUCCESS**; `Host='127.0.0.1:port'`, SNI=None (IP için SNI gönderilmez) |

Sunucu tarafı `client_connected` kanıtı (socket pin'li IP'ye bağlandı, Host/SNI orijinal hostname'te kaldı):
`dialed_target_ip_port=['127.0.0.1', 45461]`, `Host='localhost:45461'`, SNI=`'localhost'`.

**Ölçülen davranış özeti:** TCP soketi pin'li IP'ye bağlanırken TLS SNI ve `Host` başlığı orijinal
hostname'te kalıyor; tek reddetme nedeni sertifika zinciri doğrulaması, SNI/hostname mismatch değil.

Ek ölçülen ayrıntı: Python `ssl.SSLSocket.accept()` handshake'i `accept()` içinde eager yapar; istemci
sertifikayı reddedince `SSLError` yutulur (`socketserver` `except OSError: return`), yani başarısız TLS
denemeleri uygulama katmanı logunda görünmez — SNI callback'i ile doğrulandı (13 bağlantının 8'i
`client_connected`'ta, kalanı yalnızca SNI eventinde).

## Simülasyon / Kontrollü Saldırgan Senaryoları

1. **İki DNS Cevabı Senaryosu:** Bir test, aynı ana bilgisayar için çağrı başına iki farklı
   DNS cevabı (güvenli IP, ardından iç IP) döndürecek şekilde ayarlanır. Eski akışta ikinci
   IP kullanılırsa test başarısız olmalı; yeni akışta bağlantı yalnızca birinci IP'ye
   kurulmalıdır (`test_opener_dials_ip_and_never_resolves_hostname`).
2. **Yönlendirme Zinciri Senaryosu:** `http://public.test/redirect` isteği
   `http://127.0.0.1/private` adresine `302` döndürür. `_pinned_fetch` her hedefi tekrar
   politikadan geçirir; `private` hedef `EgressDenied`/`FetchBlocked` fırlatır
   (`test_redirect_to_denied_host_is_blocked_and_not_fetched`).

## Bilinen Sınırlamalar

1. `http.client.HTTPSConnection.connect()` içindeki TLS sürümü el sıkışması sırasında
   soket kapanma davranışı işletim sistemine bağlıdır; test yalnızca `server_hostname`
   argümanının sağlandığını doğrular.
2. Şema kontrolü `EgressPolicy` içinde değil, `_check_hop` öncesinde uygulanan şema reddinde; bu davranış testle kilitlendi.
3. 512KB üzerindeki `robots.txt` dosyaları için `can_fetch` hâlâ yükleme zamanında
   kontrol edilir; yeniden `Content-Length` doğrulaması eklenebilir.

## Üretim / Enstrümantasyon Planı

* Her fetch yanıtının `Egress` doğrulama sonucunu (`checked_ip`, `pin_applied`,
  `redirect_chain`) yapılandırılmış log olarak yazın (gizli içerik hariç).
* Canary testleri (ör. `K8s` kontrol düzlemi, `169.254.169.254`) için ayrı bir "redteam"
  job tanımı eklenebilir; `EgressDenied` sayısı alarm eşiği olarak kullanılabilir.
* `BrowserWorker` performans metriklerine `pinned_connection_count` ve
  `redirect_revalidation_count` sayaçları eklenmeli.
