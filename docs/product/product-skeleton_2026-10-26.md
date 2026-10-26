# Ürün İskeleti — Tam Yüzey Haritası (2026-10-26)

Bu doküman, ürünün **insan ve entegratör tarafından görülen her yüzeyini** tek yerde toplar.
Amaç: "bu ne, nerede, nasıl görünüyor, boş/yükleme/hata durumunda ne oluyor" sorularına
cevap bırakmamak. Her bölüm ya gerçek koddan çıkarılmış ya da `[YOK/TASARLANACAK]` olarak
dürüftçe işaretlidir. Uydurma alan adı yok; hepsi `src/` içinden doğrulanmıştır.

İlgili diğer dokümanlar:
- `docs/product/competitive-benchmark_2026-10-26.md` — rakip karşılaştırma sayıları.
- `docs/product/human-face-review_2026-10-26.md` — cila öncesi insan-yüzü değerlendirmesi.

---

## 0. Ürün bir cümlede

Web verisini **çeken, temizleyen, akıllıca yönlendiren** bir motor + API: bir URL'i/aramayı
alır, motor merdiveniyle (lightpanda → Chromium) getirir, reklam/izleyici temizler, temiz
markdown + keşfedilen API uçları döner; ayrıca sorguyu fan-out'a böler ve modeli akıllı router
ile seçer.

---

## 1. Yüzey envanteri (kim, nereden kullanıyor)

| Yüzey | Dosya | Kullanıcı | Durum |
|---|---|---|---|
| REST API (browse/search/chat/router) | `src/api/server.py` | entegratör, diğer servisler | var |
| MCP sunucusu (4 araç) | `src/mcp_server.py` | AI asistan (Hermes vs) | var |
| Sohbet çıktısı (benim ürettiğim metin) | Hermes/Telegram | son kullanıcı | var |
| Web UI / landing / dashboard / ayar | — | son kullanıcı | **[YOK]** |
| Karşılama / ilk açılış ekranı | — | son kullanıcı | **[YOK]** |
| Görsel kimlik (logo/renk/tipo) | — | son kullanıcı | **[YOK]** |

---

## 2. REST API yüzeyi (gerçek uçlar, `src/api/server.py`)

Tüm yanıtlar JSON (`Content-Type: application/json`). Kimlik: `/v1/jobs/*` ve `/v1/search/fanout`
`Authorization: Bearer <BROWSE_API_KEY>` ister (env set ise, sabit zamanlı karşılaştırma).
Router uçları (`/v1/chat/completions`, `/v1/router/*`, `/v1/models`) bilerek açıktır (Hermes için).
Rate limit: `/v1/jobs/*` + `/v1/search/fanout` (`ORACLE_JOBS_RPM`, vars 60) → **429** + `Retry-After`.

### 2.1 `POST /v1/jobs/browse` — URL çek
İstek:
```json
{
  "url": "https://ornek.com/makale",
  "goal": "makalenin ana argümanı",        // opsiyonel
  "needs_vision": false,                    // opsiyonel
  "js_complexity": "low",                   // "low"|"medium"|"high"
  "webhook_url": "https://..."             // opsiyonel
}
```
Yanıt (200) — `create_job` alanları + koşu sonuçları:
```json
{
  "job_id": "job_abc123", "session_name": "farm_job_abc123",
  "target_url": "...", "goal": "...", "needs_vision": false, "js_complexity": "low",
  "webhook_url": null,
  "status": "completed",                     // queued|running|completed|failed
  "engine": "lightpanda",                    // son kullanılan motor
  "extracted_markdown": "...temiz markdown...",
  "oracle_passed": true,                     // içerik doğrulaması geçti mi
  "created_at": 1730..., "updated_at": 1730...,
  "discovered_apis": [{"url": "/api/product", "method": "GET", "kind": "xhr"}],
  "attempted_engines": ["lightpanda"],
  "blocked": false,                          // robots/policy engeli
  "webhook_delivery": {...}                  // yalnız webhook verildiyse
}
```
Hatalar: **400** (`{"error": "<hedef doğrulama>"}`, SSRF/özel-IP, boş url), **401**, **429**.

### 2.2 `GET /v1/jobs/<job_id>` — iş durumu
Yanıt: yukarıdaki job nesnesi. **404** `{"error": "Job not found: <id>"}`.

### 2.3 `POST /v1/search/fanout` — sorguyu fan-out'a böl, kaynak topla
İstek: `{"query": "..."}`.
Yanıt (200) (`src/search/query_fanout.py`):
```json
{
  "original_query": "...",
  "subqueries": ["...", "..."],
  "decomposition": "lexical",                // "lexical"|"llm"
  "sources": [{"url": "...", "title": "...", "snippet": "..."}],
  "grounded_context": "[1] Başlık (url) — snippet (Alt Sorgu: '...')"
}
```
Hatalar: **400** (boş query), **502** `{"error": "search backend unavailable: <Exc>"}` (asla kaynak uydurulmaz).

### 2.4 `POST /v1/chat/completions` — OpenAI uyumlu, router'lı
İstek: OpenAI shape (`messages` nonempty, `model` sanal profil olabilir).
Akış: sanal modelse learner sinyali → MoA (kapalı) → `plan_with_context` ile uygun modeller.
Hatalar: **400** (messages), **400** (Unknown model), **422** (No verified eligible model...).
Yanıt: upstream LLM yanıtı iletilir (OpenAI shape).

### 2.5 Router/telemetri uçları (GET)
- `/v1/models` — servis edilen modeller.
- `/v1/models/profiles` — AA/maliyet/pencere profilleri.
- `/v1/health` → `{"status":"ok|degraded","upstream_ready":bool,"registry":{...},"watchdog":{...}}`.
- `/v1/router/learning` — outcome-learning durumu.
- `POST /v1/router/moa` — MoA politika ayarı (kapalı vars).
- `POST /v1/router/complete` — **501** (eski sentetik yol kapalı).
Diğer her şey → **404** `{"error": "Unknown endpoint"}`.

---

## 3. Ortak hata şeması (mevcut durum + hedef)

**Mevcut:** `{"error": "<serbest metin>"}` + uygun HTTP kodu (400/401/404/422/429/501/502).
**Eksik / cila önerisi:** stabil `code`, `request_id`, `hint` alanı:
```json
{"error": {"code": "target_private_address", "message": "özel/loopback hedef reddedildi",
           "request_id": "req_...", "hint": "herkese açık bir URL deneyin"}}
```
Bu tutarlılık, entegratör için "kafa soru işareti kalmasın" şartının parçasıdır.

### 3a. Erişim engeli kodları (onaylandı — bilgi özgürlüğü ilkesi)
Engel sessizce atlatılmaz; her red makine-okunur bir kodla ve insan dilinde açıklamayla döner.

| code | HTTP | Anlam | Kullanıcıya mesaj (örnek) |
|---|---|---|---|
| `robots_disallowed` | 403 | Site robots.txt ile bu yolu yasaklıyor | "Bu sitenin robots.txt dosyası bu sayfanın taranmasını yasaklıyor." |
| `blocked_by_site` | 403 | Site bizi (veya bu tarayıcı tipini) engelledi; `domain` alanıyla döner | "{domain} bu erişimi engelledi. Bu engel atlatılmaz." |
| `captcha_required` | 403 | Sayfa CAPTCHA istiyor; çözülmez | "Bu sayfa CAPTCHA istiyor. Siz çözüp tekrar deneyebilirsiniz." |
| `paywall_or_login_required` | 402/401 | Üyelik/ödeme arkası içerik; çekilmez | "Bu içerik üyelik gerektiriyor; içerik alınmadı." |
| `rate_limited_by_site` | 429 | Site hız sınırı; bizde bekleme + `retry_after` | "Site istek sınırına ulaştı. {retry_after} sn sonra deneyin." |

Kurallar: sessiz boş sayfa **yok**; her red `request_id` ve `domain` (varsa) taşır; kod seti sabittir.

Örnek:
```json
{"error": {"code": "blocked_by_site", "message": "example.com bu erişimi engelledi. Bu engel atlatılmaz.",
           "request_id": "req_...", "domain": "example.com", "hint": "Siteyle iletişime geçebilir veya kendi tarayıcı oturumunuzla deneyebilirsiniz."}}
```


---

## 4. MCP yüzeyi (`src/mcp_server.py` — 4 araç)

| Araç | Girdi | Çıktı | Not |
|---|---|---|---|
| `browse_url` | `url`, `goal`, `needs_vision` | temiz markdown + keşfedilen API uçları | motor merdiveni + robots |
| `search_fanout` | `query` | deduped kaynaklar + `[N]` grounding | |
| `list_models` | — | router'ın servis ettiği modeller | |
| `router_health` | — | watchdog + upstream hazır mı | |

Her araç REST'e loopback'ten gider; Bearer anahtarı `BROWSE_API_KEY` env, değilse `~/.config/oracle-router/browse_api.env`.

---

## 5. Durum makinesi & boş/yükleme durumları (insan yüzü için kritik)

**Job yaşam döngüsü:** `queued → running → completed | failed`.
- `oracle_passed=false` → `status="failed"` (içerik doğrulanamadı).
- `blocked=true` → politika/robots engeli (merdiven asla tırmanmaz, fail-open değil).
- **Yükleme durumu:** `[YOK/TASARLANACAK]` — LLM turu saniyeler sürebilir; kullanıcı "çalışıyor mu" görsün (spinner/ilerleme). Motor hızlı (20–65 ms), gecikme LLM turunda.
- **Boş durumlar (şu an ham/çıplak):** sonuç yok, arama boş, iş başarısız, robot engeli. Her biri için insan-dili mesaj `[TASARLANACAK]`.
- **Hata sayfası:** teknik mesajlar son kullanıcıya sızıyor; maskeleme + insan dili `[TASARLANACAK]`.

---

## 6. Görsel kimlik & karşılama `[TASARLANACAK]`

- Logo/wordmark, renk paleti, tipografi, spacing ölçeği.
- Karşılama/ilk açılış: "bu ne işe yarar → ilk komutun ne" 10 saniyede anlaşılsın.
- Yükleniyor/boş/hata durumlarının tasarımı (bkz. §5).
- (Detay: `human-face-review_2026-10-26.md`, "çıkış öncesi 5 madde".)

---

## 7. Performans yüzü (özet — detay benchmark raporunda)

- Motor fetch: **static 20.4 ms / spa 63.7 ms / heavy 23.9 ms**, **~17 MiB**, %100 başarı.
- Rakiplere göre **~2× (en yakın) – ~5× (masaüstü tarayıcı) hızlı**, **~10–35× hafif**.
- Bu sayılar "insan yüzü" tasarımına da yön verir: motor hızlı olduğu için gecikme LLM turundan gelir, arayüz akış/akış yanıt vermeli.

---

## 8. Kapsam sınırı (dürüst)

- Bu iskelet, ürünün **mevcut** yüzeylerini ve eksiklerini işaretler; `* [TASARLANACAK]` satırları
  henüz görsel olarak var olmayan yüzlerdir (kod değil, tasarım).
- Rakip/fiyat/LLM kalite iddiaları ayrı dokümanlarda; burada yalnız mimari yüzey var.
