"""Download/verify/extract browser binaries into ~/.local/share/bench-browsers (no root)."""
import hashlib
import json
import os
import urllib.request
import zipfile
from typing import Dict, Tuple

ROOT = os.path.expanduser("~/.local/share/bench-browsers")
MANIFEST = os.path.join(ROOT, "manifest.json")
CFT_URL = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"


def pick_cft_urls(data: dict, channel: str, platform: str) -> Tuple[str, Dict[str, str]]:
    ch = data["channels"][channel]
    urls = {}
    for binary in ("chrome", "chrome-headless-shell"):
        for item in ch["downloads"].get(binary, []):
            if item["platform"] == platform:
                urls[binary] = item["url"]
    return ch["version"], urls


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: str) -> str:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    urllib.request.urlretrieve(url, dest)
    return sha256_file(dest)


def unzip_keep_modes(path: str, dest: str) -> None:
    with zipfile.ZipFile(path) as z:  # zipfile drops exec bits; restore from external_attr
        for info in z.infolist():
            z.extract(info, dest)
            mode = info.external_attr >> 16
            if mode:
                os.chmod(os.path.join(dest, info.filename), mode)


def record(target_id: str, exe: str, version: str, source: str, sha256: str, kind: str = "chromium") -> None:
    os.makedirs(ROOT, exist_ok=True)
    data = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else {}
    data[target_id] = {"exe": exe, "version": version, "source": source, "sha256": sha256, "kind": kind}
    json.dump(data, open(MANIFEST, "w"), indent=2)
