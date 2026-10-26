# Ürünün "İnsan Yüzü" Değerlendirmesi (2026-10-26)

Teknik olarak ürün çalışıyor (benchmark: fetch 20-65 ms, 17 MiB; 502 test yeşil).
Ama insanla temas eden yüzler daha önce tek tek ele alınmamıştı. Bu rapor o boşluğu
kapatır: **ne var, ne kötü, ne yok, çıkış öncesi şart vs sonrası.**

## 1. Ne var (insanla temas eden yüzler)

| Yüz | Durum | Kim kullanıyor |
|---|---|---|
| REST API (`/v1/jobs/browse`, `/v1/search/fanout`, `/v1/chat/completions`, router uçları) | çalışıyor | geliştirici / entegratör |
| MCP sunucusu (`src/mcp_server.py`: `browse_url`, `search_fanout`, `list_models`, `router_health`) | çalışıyor | AI asistanlar (Hermes vs) |
| Sohbet çıktısı (Hermes/Telegram üzerinden benim ürettiğim metin) | çalışıyor | son kullanıcı (şimdilik sen) |
| Web UI / landing / dashboard / ayar paneli | **YOK** | — |

Yani bugün "insan yüzü" fiilen **benim sohbet çıktım** ve **API/MCP JSON'u**. Görsel bir ürün yüzü yok.

## 2. Ne kötü (kullanılabilir ama güven vermiyor / çirkin)

- **JSON hata şekli tutarsız.** Çoğu uçta `{"error": "..."}` var ama stabil hata kodu yok
  (400/401/404/422/502 karışık, mesajlar tek tek yazılmış). Entegratör için ayrıştırması zor:
  `"query must be a non-empty string"` gibi string'lere bakmak gerekiyor. Öneri: `{"error": {"code": "...", "message": "...", "request_id": "..."}}`.
- **`request_id` yok.** Hata ayıklama ve destek için her yanıtta bir korelasyon kimliği olmalı.
- **Rate limit + auth hata mesajları minimal** (`{"error": "rate limit exceeded"}`, `"Unauthorized"`).
  Retry-After var (iyi) ama "neden" ve "ne yapmalısın" yok.
- **Başarılı `browse` çıktısı düz metin markdown + ham JSON karışımı** — alan adları belgelenmemiş,
  örnek yanıt yok. Entegratör ne döneceğini bilmeden denemek zorunda.

## 3. Ne yok (kör noktalar — çıkış öncesi mutlaka düşünülmeli)

- **İlk açılış / karşılama deneyimi yok.** Ürünü ilk kez gören biri "bu nedir, ne işe yarar,
  ilk komutum ne olmalı" sorusuna bir yüze bakarak cevap bulamıyor.
- **Boş durum (empty state) tasarımı yok.** Sonuç gelmezse, arama boşsa, job başarısızsa kullanıcı
  ne görüyor? Şu an muhtemelen boş/ham JSON.
- **Yükleme/ilerleme göstergesi yok.** Fetch 20-65 ms ama LLM turu saniyeler sürebilir; kullanıcı
  "acaba çalışıyor mu" diye bekliyor. (Not: motor hızlı, gecikme LLM turunda — tasarım buna göre olmalı.)
- **Marka/renk/tipografi/logo yok.** "Ucuz AI çıktısı" hissi vermemek için minimum görsel kimlik gerek.
- **Hata sayfaları/insan dili yok.** Teknik hata mesajları son kullanıcıya doğrulmamış şekilde sızabilir.

## 4. Ayrım: çıkış öncesi şart cila vs çıkış sonrası cila

**Çıkış öncesi MUTLAKA (insan ürüne dokunmadan güven versin):**
1. Minimum görsel kimlik: logo/wordmark, renk paleti, tipografi, temel spacing.
2. Karşılama/ilk açılış ekranı (ürün ne yapar, ilk adım ne).
3. Hata mesajlarını insan diline çevirme + `request_id`.
4. Yükleniyor/ilerleme durumu (özellikle LLM turu süresince).
5. Boş durum tasarımları (sonuç yok, hata, robot engeli).

**Çıkış sonrası (iteratif, ölçüye göre):**
- Dashboard/ayar paneli, kullanım istatistikleri.
- Mikro etkileşim, animasyon, tema seçenekleri.
- Detaylı dokümantasyon sitesi, örnek galerisi.

## 5. Tavsiye

Motor tarafı hazır ve hızlı (benchmark kanıtlı). Sırada **cılanın minimum insan yüzü**
kısmı var: yukarıdaki "çıkış öncesi" 5 madde. Bunlar yapılmadan ürün "teknik olarak çalışıyor"
olur ama insana **güven vermez**. Hedef: bir insan ilk ekrana bakıp 10 saniyede "bu ne işe yarar,
şimdi ne yapayım" sorusunun cevabını görsün.
