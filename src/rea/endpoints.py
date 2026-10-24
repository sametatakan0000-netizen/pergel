"""Endpoint extraction from text/JS bundles (passive static analysis)."""
import re
from typing import List

_URL = re.compile(r"""(?:https?|wss?)://[^\s"'`<>\\)\]}]+""", re.IGNORECASE)
_NOISE_HOSTS = ("w3.org", "json-schema.org", "schemas.xmlsoap.org", "ns.adobe.com", "purl.org",
                "xmlns.com", "example.org", "localhost", "127.0.0.1", "0.0.0.0")


def extract_endpoints(text: str) -> List[str]:
    seen, out = set(), []
    for raw in _URL.findall(text):
        url = raw.rstrip(".,;:!?)")
        host = re.sub(r"^[a-z]+://", "", url, flags=re.IGNORECASE).split("/")[0].split(":")[0].lower()
        if any(host == n or host.endswith("." + n) for n in _NOISE_HOSTS):
            continue
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out
