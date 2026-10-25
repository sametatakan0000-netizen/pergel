# REA: Alpine Linux 3.24.3 & Fedora Workstation 44 (Live ISO)

## Doğrulama (resmi checksum)
- Alpine standard 3.24.3 x86_64 ISO sha256 `1629ffe7…12be` — resmi `.sha256` ile eşleşti.
- Fedora Workstation Live 44-1.7 x86_64 ISO sha256 `1620295f…6ddf` — resmi CHECKSUM ile eşleşti.

## Kurulum mimarisi
- Alpine: `boot/modloop-lts` (squashfs modloop), `boot/initramfs-lts`, kernel 6.18.58-0-lts. syslinux + GRUB EFI.
- Fedora: `LiveOS/squashfs.img` (2.48 GB) bir **EROFS** imajı (SquashFS değil; LZ4, BIG_PCLUSTER). Kernel 6.19.10-300.fc44. Live CDLABEL `Fedora-WS-Live-44`.
  - Ürün için çıkarım: install/live imaj ayrıştırıcısı SquashFS'e ek olarak EROFS desteklemeli.

## Dinamik boot (KVM, seri konsol, `-kernel/-initrd` direct boot)
- Alpine 3.24: `Welcome to Alpine Linux 3.24` + `localhost login:` prompt'u yakalandı (login'e kadar).
- Fedora 44: dracut → `Welcome to Fedora` banner'ı yakalandı; 150 sn limitinde login prompt'una ulaşılamadı (süre sınırı, hata değil).
- Ubuntu 26.04.1 (önceki tur): systemd `boot-complete`, `network-online`, `cloud-config` hedefleri; FAILED satırı yok.

## Bilinen sınırlar
- Windows eval ISO: Microsoft Eval Center kayıt formu + zamanlı link gerektirir; otomatik çekilmedi (kayıt formuna sahte bilgi girilmedi).
- EROFS içerik çıkarımı için `erofs-utils` gerekir; sudo etkileşimli şifre istediği için kurulamadı. Rootfs içerik envanteri yapılmadı.
- Alpine ve Fedora için paket/CDP/eklenti analizi yapılmadı (sadece boot ve imaj yapısı).
