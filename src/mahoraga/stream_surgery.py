"""Stream cerrahisi yardımcıları: shard tamamlık doğrulaması."""
import json
import os
import struct


def safetensors_complete(path) -> bool:
    """Bir safetensors dosyasının bütünüyle inmiş/bozulmamış olduğunu doğrula.

    Header'daki data_offsets sonuna göre beklenen toplam boyutu hesaplar
    ve dosya boyutuyla karşılaştırır. mmap hatasının tek sebebi eksik
    dosyadır; bu kontrol indirilmemiş shard için yeniden indirmeyi,
    tam shard için gereksiz yeniden indirmeyi engeller.
    """
    p = str(path)
    try:
        fs = os.path.getsize(p)
    except OSError:
        return False
    if fs < 8:
        return False
    try:
        with open(p, "rb") as f:
            hl = struct.unpack("<Q", f.read(8))[0]
            if hl <= 0 or hl > fs - 8:
                return False
            hdr = json.loads(f.read(hl))
        end = 0
        for v in hdr.values():
            if isinstance(v, dict) and "data_offsets" in v:
                end = max(end, v["data_offsets"][1])
        return fs == end + 8 + hl
    except Exception:
        return False
