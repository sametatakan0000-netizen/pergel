"""Pergel marka kabuğu: Chromium `.pak` kaynak paketlerini yeniden markala.

Chromium, ürün adı dizgelerini (``Google Chrome for Testing``, ``Chromium``)
locales/*.pak içinde UTF-8 yüklerle tutar; pencere başlığı, Hakkında kutusu
ve chrome:// sayfaları buradan beslenir.

Gerçek v5 .pak düzeni (Chromium 156, ``ui/base/resource/data_pack.cc`` ile
doğrulandı):

- Başlık (12 B): ``uint32 version``, ``uint8 encoding``, 3 B dolgu,
  ``uint16 resource_count``, ``uint16 alias_count``.
- Kaynak tablosu: ``(count + 1) × {uint16 id, uint32 offset}``. Sondaki
  kayıt sentinel'dir: son öğenin UZUNLUĞU iki ofset farkıdır.
- Alias tablosu: ``alias × {uint16 giriş indeksi, uint16 kaynak id}``.
- Veri bölgesi ofsetlerin bittiği yerde başlar; kaynak ofsetleri indeks
  sırasında artan olmalıdır (Chromium doğrular). Kayıt uzunlukları her
  zaman bir sonraki kaydın ofset farkıdır; aynı ofset = sıfır uzunluk.

Yeniden markalama yükleri değiştirip ofsetleri yeniden yazar; id sırası,
sentinel ve alias tablosu korunur.
"""
from __future__ import annotations

import os
import re
import struct
from pathlib import Path

_HEADER = struct.Struct("<IB3sHH")  # ver, kodlama, dolgu, count, alias
_ENTRY = struct.Struct("<HI")  # id, offset


class PackError(ValueError):
    pass


# Marka kuralları: (aranan, yerine konan). Önce regex kuralları.
BRAND_RULES = (
    (re.compile(rb"Google Chrome for Testing"), b"Pergel Browser"),
    (re.compile(rb"Chrome for Testing"), b"Pergel Browser"),
    (re.compile(rb"Google Chrome"), b"Pergel Browser"),
    (re.compile(rb"Google Chromium"), b"Pergel"),
    (re.compile(rb"Chromium Dev"), b"Pergel Dev"),
    (re.compile(rb"Chromium"), b"Pergel"),
    (re.compile(rb"\bChrome\b"), b"Pergel"),
    (b"Google LLC and The Pergel Authors", b"Pergel Authors"),
    (b"Google LLC", b"Pergel Authors"),
    # Pencere başlığı biçimleri: sadece sekme adı.
    (b"$1 - $2", b"$1"),
)


def parse_pack(data: bytes) -> tuple[int, int, list[tuple[int, bytes]]]:
    """v5 .pak -> (version, encoding, [(resource_id, payload), ...])."""
    _pad, encoding, _alias, _alias_raw, entries, _sentinel, _middle = _parse(data)
    return 5, encoding, entries


def write_pack(version: int, encoding: int, entries: list[tuple[int, bytes]],
               alias_raw: bytes = b"", middle: bytes = b"",
               sentinel_id: int = 0,
               pad: bytes = b"\x00\x00\x00",
               alias_count: int = 0) -> bytes:
    """Aynı indeks sırasıyla pak yeniden yazar.

    Her kaydın ofseti bir öncekinin bitişidir; boş yükler ofseti ilerletmez
    (sıfır uzunluk korunur). Sona, uzunluğu veren sentinel kaydı yazılır.
    """
    header = _HEADER.pack(version, encoding, pad, len(entries), alias_count)
    data_start = (_HEADER.size + (len(entries) + 1) * 6
                  + len(alias_raw) + len(middle))
    offsets = []
    off = data_start
    for _, payload in entries:
        offsets.append(off)
        off += len(payload)
    index = b"".join(_ENTRY.pack(rid, offsets[i])
                     for i, (rid, _) in enumerate(entries))
    index += _ENTRY.pack(sentinel_id, off)  # sonucun uzunluğu sentinel'da
    blobs = b"".join(p for _, p in entries)
    return header + index + alias_raw + middle + blobs


def rebrand_pack(data: bytes, rules: tuple = BRAND_RULES) -> bytes:
    pad, encoding, alias_count, alias_raw, entries, sentinel, middle = _parse(data)

    def apply(payload: bytes) -> bytes:
        for pat, rep in rules:
            payload = (pat.sub(rep, payload) if isinstance(pat, re.Pattern)
                       else payload.replace(pat, rep))
        return payload

    new_entries = [(rid, apply(p)) for rid, p in entries]
    if new_entries == entries:
        return data
    return write_pack(5, encoding, new_entries, alias_raw, middle,
                      sentinel, pad, alias_count)


def rebrand_file(path: str | os.PathLike[str], rules: tuple = BRAND_RULES) -> int:
    """Dosyayı yerinde yeniden markalar; yanına ``.orig`` yedeği bırakır.

    Değişim bayt sayısı (mutlak) döner; değişiklik yoksa 0.
    """
    p = Path(path)
    raw = p.read_bytes()
    new = rebrand_pack(raw, rules)
    if new == raw:
        return 0
    bak = p.with_suffix(p.suffix + ".orig")
    if not bak.exists():
        bak.write_bytes(raw)
    p.write_bytes(new)
    return abs(len(raw) - len(new))


def _parse(data: bytes):
    if len(data) < _HEADER.size:
        raise PackError("pack too short")
    version, encoding, pad, count, alias_count = _HEADER.unpack_from(data, 0)
    if version != 5:
        raise PackError(f"unsupported pack version {version}")
    index_start = _HEADER.size
    n_index = count + 1  # sentinel dahil
    table_end = index_start + n_index * 6 + alias_count * 4
    if table_end > len(data):
        raise PackError("pack too short for index/alias tables")
    idx = [_ENTRY.unpack_from(data, index_start + i * 6) for i in range(n_index)]
    alias_raw = data[index_start + n_index * 6:table_end]
    offsets = [off for _, off in idx]
    if any(a > b for a, b in zip(offsets, offsets[1:])):
        raise PackError("pack offsets not non-decreasing")
    if offsets[0] < table_end:
        raise PackError("data region overlaps tables")
    middle = data[table_end:offsets[0]]  # olası hizalama dolgusu
    entries = []
    for i in range(count):
        rid, off = idx[i]
        end = idx[i + 1][1]
        entries.append((rid, data[off:end]))
    sentinel_id, sentinel_off = idx[count]
    return pad, encoding, alias_count, alias_raw, entries, sentinel_id, middle
