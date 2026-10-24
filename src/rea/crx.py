"""CRX3 / ZIP extension unpacker (pure, in-memory; no files written, zip-slip safe)."""
import io
import struct
import zipfile
from typing import Dict


def extract_crx(data: bytes) -> Dict[str, bytes]:
    """Return {path: bytes}. Accepts CRX3 ('Cr24' + version + header length) or a plain ZIP."""
    if data[:4] == b"Cr24":
        version, header_len = struct.unpack("<II", data[4:12])
        if version not in (2, 3):
            raise ValueError(f"unsupported CRX version {version}")
        # shortcut: CRX2 has two length fields (pubkey+sig); only CRX3 layout is parsed precisely, upgrade if a CRX2 sample matters
        offset = 12 + header_len if version == 3 else 16 + struct.unpack("<II", data[8:16])[0] + struct.unpack("<II", data[8:16])[1]
        payload = data[offset:]
    elif data[:2] == b"PK":
        payload = data
    else:
        raise ValueError("not a CRX or ZIP file")
    files: Dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        for info in z.infolist():
            name = info.filename
            if info.is_dir() or name.startswith("/") or ".." in name.split("/"):
                continue  # zip-slip: never accept escaping paths
            files[name] = z.read(info)
    return files
