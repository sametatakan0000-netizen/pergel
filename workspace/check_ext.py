#!/usr/bin/env python3
"""Check the live instance: extension loaded? chrome://newtab overridden?"""
import asyncio
import json
import os
import sys
import urllib.request

PROFILE = "/home/pc/.config/vane/profile"
EXT_ID = "pigpidnbkgjjnfcjmkleeikaoigfkdbn"


def targets(port: int) -> list:
    with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json", timeout=5) as r:
        return json.load(r)


async def nav(ws, ws_id, url: str) -> str:
    await ws.send(json.dumps({"id": ws_id, "method": "Page.navigate",
                              "params": {"url": url}}))
    while True:
        m = json.loads(await ws.recv())
        if m.get("id") == ws_id:
            return json.dumps(m.get("result", {}))[:80]


async def main() -> int:
    port = int(open(os.path.join(PROFILE,
                                 "DevToolsActivePort")).readline())
    import websockets  # type: ignore
    ts = targets(port)
    page = next(t for t in ts
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl"))
    async with websockets.connect(page["webSocketDebuggerUrl"],
                                  max_size=2**26) as ws:
        r1 = await nav(ws, 1, f"chrome-extension://{EXT_ID}/vane_ntp.html")
        await asyncio.sleep(2)
        r2 = await nav(ws, 2, "chrome://newtab")
        await asyncio.sleep(2)
    ts = targets(port)
    print("ext page nav:", r1)
    print("newtab nav:", r2)
    for t in ts:
        if t.get("type") == "page":
            print("  page:", t["url"][:110])
    urls = [t.get("url", "") for t in ts if t.get("type") == "page"]
    ext_ok = any(f"chrome-extension://{EXT_ID}" in u for u in urls)
    ntp_ok = any("vane_ntp.html" in u for u in urls)
    print("EXT_LOADED:", "OK" if ext_ok else "FAIL",
          "| NTP_PRESENT:", "OK" if ntp_ok else "FAIL")
    return 0 if ext_ok and ntp_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
