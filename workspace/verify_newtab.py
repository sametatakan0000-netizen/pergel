#!/usr/bin/env python3
"""Verify a REAL Ctrl+T opens a NEW Vane NTP tab (not Google / plain newtab).

Strict: the new tab must be a NEW target whose URL is the Vane NTP.
"""
import asyncio
import json
import os
import sys
import urllib.request

PROFILE = "/home/pc/.config/vane/profile"


def targets(port: int) -> list:
    with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json", timeout=5) as r:
        return json.load(r)


async def main() -> int:
    port = int(open(os.path.join(PROFILE,
                                 "DevToolsActivePort")).readline())
    import websockets  # type: ignore
    before = {t["id"] for t in targets(port)}
    ts = targets(port)
    page = next(t for t in ts
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl"))
    async with websockets.connect(
            json.load(urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=5)
            )["webSocketDebuggerUrl"], max_size=2**26) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Target.createTarget",
                                  "params": {"url": "chrome://newtab"}}))
        while True:
            m = json.loads(await ws.recv())
            if m.get("id") == 1:
                break
    await asyncio.sleep(4)
    new = [t for t in targets(port) if t["id"] not in before
           and t.get("type") == "page"]
    print("new tabs after Ctrl+T:")
    ok = False
    for t in new:
        print("  +", t["url"][:110])
        if "vane_ntp.html" in t.get("url", ""):
            ok = True
        if "google." in t.get("url", "") or t.get("url", "").startswith(
                "chrome://newtab"):
            ok = False
    print("REAL_CTRL_T:", "OK" if ok else
          f"FAIL (new={[t['url'][:60] for t in new]})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
