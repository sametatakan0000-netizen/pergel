import asyncio, base64, json, sys, urllib.request
import websockets

PORT = sys.argv[1]
OUT = sys.argv[2]


async def main():
    pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
    pg = [p for p in pages if p["type"] == "page"][0]
    async with websockets.connect(pg["webSocketDebuggerUrl"], max_size=20 * 1024 * 1024) as ws:
        n = 0

        async def call(m, p=None):
            nonlocal n
            n += 1
            await ws.send(json.dumps({"id": n, "method": m, "params": p or {}}))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == n:
                    return r

        await call("Page.enable")
        await asyncio.sleep(1)
        r = await call("Page.captureScreenshot", {"format": "png"})
        data = base64.b64decode(r["result"]["data"])
        with open(OUT, "wb") as f:
            f.write(data)
        print("saved", OUT, len(data))

asyncio.run(main())
