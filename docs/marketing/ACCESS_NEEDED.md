# 🔑 Pergel Pazarlama — Erişim Listesi

> Agent'ın otonom çalışabilmesi için gereken hesaplar ve erişimler.
> Her madde: **Ne lazım** → **Nereden alınır** → **Nasıl verilir**.

---

## 1. Hacker News (Show HN)
- **Ne lazım**: HN hesabı (username + password)
- **Nereden**: https://news.ycombinator.com/login → "Create Account"
- **Nasıl verilir**: Telegram'dan kullanıcı adı + parola gönder. Vault'a kaydedilir.
- **Not**: Yeni hesap = düşük karma. HN'de eski hesaplar daha güvenilir. Varsa mevcut hesap kullan.

## 2. Reddit
- **Ne lazım**: Reddit hesabı (username + password)
- **Nereden**: https://www.reddit.com/register
- **Nasıl verilir**: Telegram'dan kullanıcı adı + parola. Vault'a kaydedilir.
- **Not**: Hesabın yaşı ve karma'sı önemli. Yeni hesap = shadowban riski. Varsa mevcut hesap.

## 3. X/Twitter
- **Ne lazım**: İki seçenekten biri:
  - **A)** xurl için API key: https://developer.x.com → App oluştur → Bearer Token
  - **B)** Tarayıcı otomasyonu: X hesabı (username + password)
- **Nasıl verilir**: API key veya parola Telegram'dan.
- **Not**: xurl ücretsiz katmanı 500 post/ay.

## 4. Dev.to
- **Ne lazım**: Dev.to API key
- **Nereden**: https://dev.to/settings/extensions → "DEV Community API Keys" → Generate
- **Nasıl verilir**: API key Telegram'dan. (Sadece string, güvenli)

## 5. Product Hunt
- **Ne lazım**: PH hesabı (email + parola)
- **Nereden**: https://www.producthunt.com/sign-up
- **Nasıl verilir**: Email + parola Telegram'dan.
- **Not**: Maker profili oluştur, GitHub linkini ekle.

## 6. Skool
- **Ne lazım**: Skool hesabı (email + parola)
- **Nereden**: https://www.skool.com/signup
- **Nasıl verilir**: Email + parola Telegram'dan.
- **Not**: İlgili topluluklara katıl (AI, dev tool, indie hacker).

## 7. LinkedIn (opsiyonel)
- **Ne lazım**: LinkedIn hesabı (email + parola)
- **Nasıl verilir**: Telegram'dan.
- **Not**: Profesyonel profil, Pergel projesini ekle.

---

## 🚀 Hızlı Başlangıç (minimum)

En azından şunlar yeterli (gerisi sonra eklenir):

| # | Platform | Öncelik | Neden |
|---|---|---|---|
| 1 | **Hacker News** | ⭐⭐⭐ | Ana lansman kanalı |
| 2 | **Reddit** | ⭐⭐⭐ | 2. büyük kanal |
| 3 | **Dev.to API key** | ⭐⭐ | Kolay alınır, hemen kullanılır |
| 4 | **X/Twitter** | ⭐⭐ | Thread + engagement |

---

## 📋 Verme Formatı (Telegram)

Şu formatta gönder (her satır bir platform):

```
HN: kullanıcı_adı / parola
Reddit: kullanıcı_adı / parola
DevTo: api_key_string
X: kullanıcı_adı / parola
PH: email / parola
Skool: email / parola
```

**Güvenlik**: Tüm bilgiler Vault'a kaydedilir, loglarda görünmez.

---

## 🤖 Otonom Akış (erişimler geldikten sonra)

```
1. Agent içerikleri otomatik üretir (TR+EN, platform-özel)
2. Taslaklar /home/pc/.hermes/cache/scratch/pergel-marketing/ altına yazılır
3. Kullanıcı Telegram'dan "onayla" der
4. Agent platformlara otomatik post eder (browser_exec / API)
5. Engagement takibi yapılır (cronjob)
```

**Kullanıcı elle hiçbir şey yazmaz, hiçbir platforma girmez.**
