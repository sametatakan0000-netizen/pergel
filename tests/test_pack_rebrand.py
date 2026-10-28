"""Pak yeniden markalama motoru testleri (gerçek v5 düzeni: sentinel + alias)."""
import struct

import unittest

from src.brand.pack_rebrand import PackError, parse_pack, rebrand_pack, write_pack, _parse


def _make_pack(entries, sentinel_id=0xFFFF, alias=b"", encoding=2):
    """Gerçekçi v5 pak üret: (count+1) indeks kaydı + sentinel + alias."""
    count = len(entries)
    table_end = 12 + (count + 1) * 6 + len(alias)
    off = table_end
    idx = b""
    blobs = b""
    for rid, payload in entries:
        idx += struct.pack("<HI", rid, off)
        blobs += payload
        off += len(payload)
    idx += struct.pack("<HI", sentinel_id, off)  # sentinel: son uzunluğu verir
    header = struct.pack("<IB3sHH", 5, encoding, b"\x00\x00\x00", count,
                         len(alias) // 4)
    return header + idx + alias + blobs


def test_parse_pack_reads_real_v5_layout():
    pak = _make_pack([(5, b"Chrome"), (6, b"Google Chrome for Testing"),
                      (7, b"xxChromiumxx")])
    ver, enc, entries = parse_pack(pak)
    assert ver == 5 and enc == 2
    assert [rid for rid, _ in entries] == [5, 6, 7]
    assert entries[1][1] == b"Google Chrome for Testing"


def test_write_pack_roundtrip_identity():
    pak = _make_pack([(5, b"Chrome"), (6, b"Google Chrome for Testing"),
                      (7, b"xxChromiumxx")],
                     sentinel_id=0xFFFE, alias=b"\x01\x00\x02\x00")
    pad, enc, alias_count, alias_raw, entries, sentinel, middle = _parse(pak)
    out = write_pack(5, enc, entries, alias_raw, middle, sentinel, pad, alias_count)
    assert out == pak


def test_rebrand_replaces_product_strings_and_keeps_layout():
    pak = _make_pack([(5, b"Chrome"), (6, b"Google Chrome for Testing"),
                      (7, b"xxChromiumxx"), (8, b"Keep $1 - $2 in sync")],
                     sentinel_id=0xFFFE, alias=b"\x02\x00\x03\x00")
    out = rebrand_pack(pak)
    ver, enc, entries = parse_pack(out)
    by_id = dict(entries)
    assert b"Chromium" not in out and b"Chrome for Testing" not in out
    assert by_id[5] == b"Pergel"
    assert by_id[6] == b"Pergel Browser"
    assert by_id[7] == b"xxPergelxx"
    assert by_id[8] == b"Keep $1 in sync"
    # düzen: sentinel ve alias tablosu korunur
    pad, e2, alias_count, alias_raw, ents, sentinel, mid = _parse(out)
    assert sentinel == 0xFFFE and alias_raw == b"\x02\x00\x03\x00"


def test_rebrand_noop_when_no_brand_strings():
    pak = _make_pack([(5, b"hello"), (6, b"world")])
    assert rebrand_pack(pak) == pak


def test_bad_header_rejected():
    with _Raises():
        parse_pack(b"\x00" * 4)
    bad = bytearray(_make_pack([(5, b"x")]))
    struct.pack_into("<I", bad, 0, 4)  # v4 desteklenmez
    with _Raises():
        parse_pack(bytes(bad))


class _Raises:
    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        assert et is not None and issubclass(et, PackError), "PackError expected"
        return True


class PackRebrandTests(unittest.TestCase):
    pass


for _n, _f in list(globals().items()):
    if _n.startswith("test_") and callable(_f):
        setattr(PackRebrandTests, _n, lambda self, _f=_f: _f())
