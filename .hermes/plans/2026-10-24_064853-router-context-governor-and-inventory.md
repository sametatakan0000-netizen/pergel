# Plan: Router bağlam yönetimi (Context Governor) + model envanteri v2 + MoA kararı + aday-farkı raporu

## Goal
Router'ın "bağlam büyüdükçe her turda daha pahalı modele sabit kalma" kaçağını kapatmak: bağlamı maliyet-bilinçli yönetmek, modelleri **etkin** bağlam penceresine göre envantere almak, MoA'yı varsayılan kapatmak ve Amiral adayları arasındaki ilk-son farkını ölçülü göstermek.

## Ölçülen durum (2026-10-24, salt-okunur; hepsi tekrar üretilebilir)
- Bugün (UTC) **$43.81**; son 1 saat $26.59; son 15 dk $16.01. Son 8 çağrının hepsi `anthropic/claude-sonnet-5.5`, her biri **~420K prompt token** (~$0.85/çağrı), bağlam tur başına büyüyor (419K -> 427K). Router fiyat hesabı doğru; kaçak **bağlam boyutu**.
- Hermes `compression.threshold = 0.5` ve pencere yüzdesi olarak çalışıyor. Router `oracle/auto` için `context_length = 1.050.000` bildiriyor (`virtual_context_length()` = havuzdaki en büyük pencere; grok-4.20 = 2.000.000). 0.5 x 1.05M = **525K**: sıkıştırma ancak 525K'da başlıyor. Tetik neredeyse hiç gelmiyor, yani "otomatik context yönetimi" teknik olarak açık ama **fiilen devre dışı**.
- Kural: tur maliyeti ≈ `prompt_tokens x giriş fiyatı`. Sonnet 5.5 için 30K = $0.075, 100K = $0.215, 420K = $0.855. Aynı bağlamda mimo-v2.6-pro 420K = ~$0.17, haiku-5.5 = ~$0.05.
- Fiyatlar `$ giriş/çıkış per 1M`; AA = Artificial Analysis zeka endeksi (registry `intelligence_index`).
- `upstream_events` tablosunda `cached_tokens` yok: önbellek isabeti ölçülmüyor, maliyet **üst sınır** tahminidir (not: gerçek fatura önbellekle daha düşük olabilir; doğrulama Task 1'de).
- MoA kanıtı: `moa_policy.db` içinde **5 gözlem, hepsi "single"**, 1 kötü. MoA'nın faydası hiç ölçülmedi.

## Aday farkı (isteğin: "birinci ile sonuncu arası fark" — mevcut politikalarla, canlı veriden)
Politikalar: (1) Pareto-dominance (35 dominated, 51 primary), (2) QUALITY_TOLERANCE=5 AA bandı içinde ucuz kazanır, (3) tier-first sıralama. 86 modelli havuz, 11 served, 10 dead.

| Başlangıç tier | #1 (Amiral) | Eşit-bant üyesi | Tur @100K | Not |
|---|---|---|---|---|
| 3 (zor) | claude-sonnet-5.5, AA 56.0, $2/$10 | 4 | $0.215 | bantta 56.0 -> 51.0 aralığı |
| 2 (orta) | sonnet-5.5:batch, AA 56.0, $1/$5 | 3 | $0.108 | aynı model, yarı fiyat (batch) |
| 1 (kolay) | deepseek-v4.1-flash, AA 39.5, $0.02/$1 | 10 | $0.004 | bant geniş: 10 aday "eşit" |

- **#1 ile son primary arası**: tier 3'te #1 = $0.215/tur@100K, son primary `step-3.7-flash:free` AA 19.5 ($0). Yani sıralama **fiyat tier'ına göre**, kalite sırasına göre değil; "son" aday ucuz ama zayıf. Tier 1'de son primary `mimo-v2.6-pro-ultraspeed` ($4.35/$8.7, AA yok) tier-1 listesinde **en pahalı çıktı** (tur@100K $0.448, lider deepseek'in **~110 katı**). Bu bir **hata sinyali**: AA'sı olmayan ve pahalı bir model primary havuzda (dominance yalnızca *bilinen* eksenlerde çalışıyor, bilinmeyen kalite = cezasız). Düzeltme Task 5.
- Pratik sonuç: farkın büyük kısmı **model seçimi değil, bağlam boyutu**. Aynı sonnet 30K'da $0.075, 420K'da $0.855 (**11,4 kat**). Seçim politikası lider ile son arasında ~50-100 kat açabilir, bağlam ise tek başına 11 kat. İkisi çarpılır.

## Mimari (3 cümle)
Üç katmanlı **Context Governor** `src/router/context_governor.py`: (a) **etkin pencere** (model başına "ekonomik bağlam": fiyat, kalite-bozulması ve bütçeden türetilir) router'ın bildirdiği `context_length`'i 1.05M'den ~200K'ya çeker, böylece Hermes'in mevcut %50 eşiği ~100K'da tetiklenir; (b) **maliyet frenı**: `plan()` turun tahmini maliyeti `ORACLE_TURN_SOFT_USD` eşiğini aşarsa daha ucuz banda iner veya `X-Oracle-Compact: advised` başlığı ve `/v1/models/context` ucu ile istemciyi uyarır; (c) **ucuz-model sıkıştırma yolu**: Hermes tarafında `compression.summary_model` ucuz bir modele sabitlenir. MoA varsayılan kapatılır; dominance filtresi bilinmeyen-kalite+pahalı modelleri eler. Router **gizli model çağrısı yapmaz** (kullanıcı kuralı): governor sadece sayar, karar verir, başlık koyar.

## Başlamadan karar noktaları (varsayılanlarla ilerler; sormadan)
- Etkin pencere varsayılanı **200K** (`ORACLE_EFFECTIVE_CONTEXT=200000`). Gerekçe: AGENTS.md kuralı "bağlamı 200K altında tut"; uzun bağlamda kalite düşüşü ("context rot") kamuya açık literatürde ölçülmüş (doğrulama Task 0'da web araştırmasıyla, SOTA kuralı).
- Yumuşak tur tavanı **$0.30** (`ORACLE_TURN_SOFT_USD`): aşınca bir alt banda iner, mutlak tavan zaten `ABSOLUTE_TURN_CAP_USD`.
- MoA: `ORACLE_MOA` varsayılan **0** (kapalı), kodu silinmez (YAGNI ihlali olmasın diye 14 gün sonra kullanılmadıysa silme maddesi Task 8).

## Görevler (her biri 2-5 dk; sıra bağımlı)

### Task 0 — SOTA doğrulaması (kod yok, 1 dosya)
Web'de ara: "long context performance degradation 2026", "prompt caching cost model Anthropic/OpenAI 2026 cache read price", "context compression agent best practices 2026". Bulguları `docs/research/context_governance_2026-10.md` içine kaynak URL'lerle yaz. Özellikle: (1) önbellek okuma fiyatı (`list_cost_cache_read` registry'de var), (2) etkin pencere için yayımlanmış eşikler (RULER/NoLiMa/LongBench v2 türevi). Doğrulama: `grep -c "https://" docs/research/context_governance_2026-10.md` >= 6. Commit: `docs(research): context governance SOTA`.

### Task 1 — Önbellek ve gerçek maliyeti ölç (RED önce)
Dosya: `tests/test_cost_model.py`, kod: `src/router/cost_model.py`.
```python
# tests/test_cost_model.py
import unittest
from src.router.cost_model import turn_cost_usd

class P:  # minimal profile stub
    billed_cost_in=2.0; billed_cost_out=10.0; list_cost_cache_read=0.2

class CostModel(unittest.TestCase):
    def test_no_cache_info_uses_full_input_price_as_upper_bound(self):
        self.assertAlmostEqual(turn_cost_usd(P, prompt=100_000, completion=1000), 0.21, places=4)
    def test_cache_read_tokens_are_priced_at_cache_rate(self):
        # 80K cached @0.2, 20K fresh @2.0, 1K out @10
        self.assertAlmostEqual(turn_cost_usd(P, 100_000, 1000, cached=80_000), 0.016+0.04+0.01, places=4)
    def test_unknown_cache_price_falls_back_to_input_price(self):
        class Q(P): list_cost_cache_read=None
        self.assertAlmostEqual(turn_cost_usd(Q, 100_000, 0, cached=80_000), 0.2, places=4)
```
Çalıştır (beklenen: `ModuleNotFoundError`): `cd $REPO && python3 -m unittest tests.test_cost_model 2>&1 | tail -3`. Sonra `src/router/cost_model.py`:
```python
def turn_cost_usd(profile, prompt: int, completion: int, cached: int = 0) -> float:
    """USD for one turn. cached tokens use the cache-read price when known, else the input price
    (upper bound — never invent a discount)."""
    pin = profile.billed_cost_in or 0.0
    pout = profile.billed_cost_out or 0.0
    pcache = profile.list_cost_cache_read if profile.list_cost_cache_read is not None else pin
    cached = max(0, min(cached, prompt))
    return ((prompt - cached) * pin + cached * pcache + completion * pout) / 1e6
```
GREEN: aynı komut -> `OK`. Ek: `upstream_events`'e `cached_tokens INTEGER` kolonu (migration `ALTER TABLE ... ADD COLUMN` try/except, `live_router.py::record_upstream` imzasına opsiyonel `cached_tokens=None`), `server.py:442` civarında `usage.prompt_tokens_details.cached_tokens` oku. Test: `record_upstream(..., cached_tokens=5)` sonra `SELECT cached_tokens` = 5. `spent_since()` yeni fonksiyonu kullanır (cached yoksa eski davranış bire bir). Commit.

### Task 2 — Etkin pencere (kaçağın asıl kapatılması)
Test önce `tests/test_context_governor.py`:
```python
import unittest
from src.router.context_governor import effective_window, advised_context_length

class Gov(unittest.TestCase):
    def test_effective_window_is_capped_by_env_default(self):
        self.assertEqual(effective_window(1_000_000, cap=200_000), 200_000)
    def test_small_models_keep_their_real_window(self):
        self.assertEqual(effective_window(32_000, cap=200_000), 32_000)
    def test_virtual_profile_reports_cap_not_max_pool_window(self):
        self.assertEqual(advised_context_length(pool_windows=[1_000_000, 2_000_000], cap=200_000), 200_000)
    def test_none_when_pool_empty(self):
        self.assertIsNone(advised_context_length([], cap=200_000))
```
`src/router/context_governor.py`:
```python
import os
DEFAULT_CAP = int(os.environ.get("ORACLE_EFFECTIVE_CONTEXT", "200000"))

def effective_window(real_window: int, cap: int = DEFAULT_CAP) -> int:
    return min(real_window, cap) if real_window else cap

def advised_context_length(pool_windows, cap: int = DEFAULT_CAP):
    ws = [w for w in pool_windows if w]
    return effective_window(max(ws), cap) if ws else None
```
`live_router.py::virtual_context_length` bu fonksiyona delege eder (davranış değişimi: 1.05M -> 200K). Test mevcut `test_*` dosyalarında 1.05M bekleyen varsa onu güncelle (`grep -rn "virtual_context_length\|1050000" tests`). Etki: Hermes `threshold 0.5` -> **100K'da** sıkıştırır (şimdi 525K). Commit.
Doğrulama (canlı, deploy sonrası): `curl -s 127.0.0.1:8090/v1/models | python3 -c "import json,sys;print([m['context_length'] for m in json.load(sys.stdin)['data'] if m['id']=='oracle/auto'])"` -> `[200000]`.

### Task 3 — Tur-başı maliyet freni (plan içinde, gizli çağrı yok)
`LiveRouter.plan_with_context` içinde tahmini prompt token (`request_features.estimate_tokens`) ile seçilen modelin `turn_cost_usd`'si `ORACLE_TURN_SOFT_USD` (varsayılan 0.30) üstündeyse: sticky bırakılır ve bir **alt banda** inilir (mevcut `_overpaying` mantığı genişletilir); alt bantta kalite farkı > `QUALITY_TOLERANCE` ise **inilmez** ama yanıt başlığına `X-Oracle-Compact: advised` + `X-Oracle-Turn-Est-USD` eklenir. Test (RED): 420K prompt, sonnet pinned, mimo-v2.6-pro/haiku mevcut -> plan ilk eleman sonnet **değildir** (bantta ucuz alternatif varsa) VEYA başlık set edilmiştir; 30K prompt -> davranış değişmez (regresyon testi). Commit.

### Task 4 — Hermes tarafı: ucuz sıkıştırma modeli + eşik (CLI, elle düzenleme yok)
```bash
hermes config set compression.threshold 0.5          # değişmez: artık 100K'da tetikler
hermes config set compression.target_ratio 0.2       # özet sonrası kuyruk ~20K
hermes config get auxiliary 2>/dev/null | head       # önce mevcut compression/summary model anahtarını gör
```
Anahtar adı Hermes dokümanından doğrulanır (`skill_view hermes-agent`; https://hermes-agent.nousresearch.com/docs): sıkıştırma özeti için `auxiliary.compression.model` benzeri anahtara **haiku-5.5 veya deepseek-v4.1-flash** yaz (sonnet değil). Doğrulama: yeni oturumda 120K'yı geçen bir konuşma sonrası `upstream_events` son satırların `prompt_tokens` değeri < 130K ve sıkıştırma turunun modeli ucuz model. Commit yok (config); not `docs/runbook`'a.

### Task 5 — Envanter v2: bilinmeyen-kalite + pahalı modeller primary'den çıkar
Bulgu: tier-1 listesinde `mimo-v2.6-pro-ultraspeed` ($4.35/$8.7, AA=None) primary'de, lider deepseek'ten ~110x pahalı. Test (RED) `tests/test_inventory_v2.py`: `intelligence_index=None` ve fiyatı tier'ın medyanının >3x'i olan model `prune_dominated` çıktısında `dominated` listesindedir; AA'sı **olan** pahalı model etkilenmez; AA=None ama **ucuz** model etkilenmez (kanıtsız kalite iddiası yok, sadece "kanıtsız + pahalı" cezası). `src/router/live_router.py::prune_dominated`'e `unproven_premium(p, tier_median_in)` kuralı ekle (sabit değil: tier medyanından türetilir). Envanter raporu: `python3 -m src.cli inventory` yeni alt komutu -> `bench/results/inventory_YYYYMMDD.md` (model, tier, AA, fiyat, served/dead, etkin pencere, **neden primary/dominated**). Doğrulama: raporda `mimo-v2.6-pro-ultraspeed` "dominated: unproven-premium" ve sayılar toplamı 86. Commit.

### Task 6 — MoA'yı varsayılan kapat (kanıtla)
`src/infra/hermes_config_builder.py:100` `"moa"` bloğu ve `server.py` MoA yolu `ORACLE_MOA=1` bayrağı arkasına alınır, varsayılan kapalı. Test: bayrak yok -> `plan_moa` çağrısı yok, tek model döner; bayrak 1 -> mevcut davranış (mevcut testler geçer). Gerekçe (README'ye 5 satır): MoA literatürde ucuz **proposer + güçlü aggregator** için kazanç gösterir, ama Hermes'te her üye **~100K+ bağlamı** tekrar okur -> N üye = N x bağlam maliyeti; 5 gözlemle (hepsi single) fayda **kanıtlanmadı**; bağlam şişikken MoA maliyeti çarpan olur. Commit.

### Task 7 — "Aday sayısı" analizi: tek mi, çok mu? (ölçülü karar, ücretsiz)
Soru: Amiral-subagent için 1 mi N aday mı? Cevap deney değil **maliyet-aritmetiği + mevcut veri** ile: `scripts/analysis/candidate_spread.py` (salt-okunur; `live_router.db` + registry) her tier ve 5 bağlam boyutu (10K/30K/100K/200K/420K) için: #1, eşit-bant üyeleri, son primary, **maliyet oranı** (son/#1), kalite farkı (AA), ve "N aday paralel" maliyeti (N=1..3) çıkarır -> `bench/results/candidate_spread_YYYYMMDD.md`. Test: sabit fixture registry ile deterministik çıktı (3 tier, beklenen oranlar sabit). Karar kuralı raporun sonuna yazılır: bir aday N>1 yalnızca (a) bant içinde ve (b) `N x tur_maliyeti <= ORACLE_TURN_SOFT_USD` ve (c) bağlam <= 30K ise; aksi halde **tek aday + yedek sıra** (şu anki fallback zinciri zaten yedek). Bu yedek zinciri "çoklu aday" ihtiyacının %90'ını karşılar: başarısız/dead model -> sıradaki, ek ödeme yok. Commit.

### Task 8 — Temizlik ve deploy
`python3 -m unittest discover -s tests -t .` hem `.venv/bin/python` hem system python'da yeşil (şu an 211 test). `scripts/host/deploy_default_router.sh` ile deploy (kullanıcı kuralı: terminal backend ssh/pc). Sonra: `curl 127.0.0.1:8090/v1/models` pencere 200000; **iki gün izleme**: `python3 -m src.cli spend --since 24h` ile günlük harcama; hedef < $5/gün (yumuşak) olağan kullanımda. 14 gün sonra `ORACLE_MOA` kullanılmadıysa moa_* dosyaları silinir (Ponytail `shortcut:` notu ile işaretle).

## Test / Doğrulama özeti
- Her görev: RED (başarısız çıktıyı göster) -> minimal GREEN -> tüm süit -> commit.
- Kabul kriterleri (hepsi ölçülebilir): (1) `oracle/auto context_length == 200000`; (2) sıkıştırma turu sonrası prompt < 130K; (3) 24 saatlik harcama < önceki 24 saatin %25'i; (4) envanter raporu 86 model, hepsi gerekçeli; (5) `candidate_spread` raporu üç tier için oran + karar kuralı içerir.
- REA kuralı (kullanıcı): her iddia ham sayıyla; tahmin işaretli ("üst sınır", "AA yok").

## Riskler / ödünleşimler
- **Etkin pencere 200K düşüyor**: 200K üstü gerçekten gereken görevlerde (büyük repo) Hermes sıkıştıracak; kayıp bilgi riski. Azaltma: `ORACLE_EFFECTIVE_CONTEXT` ile görev başına yükseltilebilir, özet kalitesi `compression` testiyle kontrol.
- **Önbellek**: sonnet/haiku prompt-cache açıksa 420K'nın çoğu ucuz okunabilir; gerçek fatura tahminden düşük olabilir. Task 1 bunu ölçmeden Task 3 eşiğini sabitleme; eşik kalibrasyonu Task 1 verisiyle.
- **Sticky + önbellek çelişkisi**: model değiştirmek önbelleği düşürür (yeni modelde ilk tur tam fiyat). Task 3 yalnızca tahmini tasarruf > önbellek kaybı ise iner.
- **AA endeksi eksik/yanıltıcı**: birkaç modelde `None`; "kanıtsız+pahalı" cezası adil ama bazı iyi modelleri geçici eler. Registry yenilendiğinde otomatik düzelir.
- **MoA kapatma**: ileride kanıt çıkarsa geri açılır (bayrak).

## Açık sorular (varsayılanla ilerler, itiraz edersen değişir)
1. Etkin pencere 200K uygun mu, yoksa 128K daha mı sıkı olsun?
2. Yumuşak tur tavanı $0.30: günlük $5 hedefine göre ~16 tur/gün; daha esnek istersen $0.50.
3. Sıkıştırma özeti için model: haiku-5.5 (güvenilir, $0.1/$0.5) mi, deepseek-v4.1-flash (en ucuz, $0.02/$1) mi? Önerim haiku (özet kalitesi riski düşük).


---
## Uygulama durumu (2026-10-24, commit'ler a1e1102 / 04fb95b)
- DONE Task 1 (cached_tokens + `cost_model.turn_cost_usd`, DB migration, 3 kayıt noktası) — 246 test.
- DONE Task 2 (etkin pencere 200K; canlıda `oracle/auto` -> 200000).
- DONE Task 5 (`unproven_premium`: canlı havuzda 10 model, hepsi benchmark'sız + hiç servis etmemiş + $4–30 giriş).
- DONE Task 6 (MoA `ORACLE_MOA` varsayılan 0).
- N/A Task 4: sıkıştırma modeli zaten `google/gemini-3.7-flash` (ucuz); eşik 0.5 x 200K = ~100K.
- AÇIK Task 3 (tur-başı maliyet freni) — cached_tokens verisi birikince kalibre edilecek.
- AÇIK Task 7 (`candidate_spread` raporu), Task 0 (SOTA araştırma notu), Task 8 (14 gün sonra MoA kodu kararı).
- Ölçüm: oturum bağlamı 420K -> ~148K; son 15 dk harcama $16.01 -> $7.70 (düzeltme sırasında, kısmi pencere).

## Güncelleme (2026-10-25 akşamı)
- **DONE Task 3** (commit `669a767`): tur-başı maliyet freni `ORACLE_TURN_BUDGET_USD`, canlıda **0.07** (0.15 iken Sonnet günde $5.33 yaktı; 24s harcama $6.75). Ölçülen tur maliyeti @130K prompt: Haiku $0.01 / GLM-Flash $0.02 / MiMo-Pro $0.05 / Sonnet $0.27. Ayrıca `ORACLE_CORE_POOL` (Haiku/GLM-Flash/MiMo-Pro/Sonnet) ve alias'ların kaldırılması (`1f16172`).
- **Etkin pencere canlıda 120K** (`ORACLE_EFFECTIVE_CONTEXT=120000`, 200K idi): Hermes sıkıştırma tetiği ~60K. Task 2 kabul kriteri (`context_length == 200000`) artık 120000 olarak güncellendi.
- **Önbellek ölçümü artık var** (`cached_tokens`, `04fb95b`) — bu planın "Task 1 verisiyle kalibre et" şartı karşılandı. 15:44 router restart'ı sonrası 53 dk / 102 tur / **$0.18** (MiMo %95 cache isabeti, Sonnet 0 tur): fren + havuz + pencere birlikte çalışıyor.
- Ek altyapı: `scripts/context_cost_guard.py` (`93e252a`, model çağrısız 24h rapor), testler hermetik (`a374c31`; `*.example.com` DNS stub, 252 test yeşil ×3).
- **Hâlâ açık:** Task 0 (`docs/research/context_governance_2026-10.md` yok), Task 7 (`scripts/analysis/candidate_spread.py` yok), Task 8 (MoA kodu silme kararı — en erken 2026-11-07).
