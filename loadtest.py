import asyncio
import json
import os
import random
import statistics
import sys
import time

import httpx

BASE = os.environ.get("BASE", "http://127.0.0.1:8000")
USERS = int(sys.argv[1]) if len(sys.argv) > 1 else 100
SEED = os.environ.get("SEED_FILE", os.path.join(os.path.dirname(__file__), "challenges.seed.json"))
EVENT_CODE = os.environ.get("EVENT_CODE", "")
FLAGS = {c["id"]: c["flag"] for c in json.load(open(SEED, encoding="utf-8"))}
lat = []
errors = []


async def timed(client, method, path, **kw):
    t = time.perf_counter()
    r = await client.request(method, path, headers={"X-FD": "1"}, **kw)
    lat.append(time.perf_counter() - t)
    return r


async def player(i, start):
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        await start.wait()
        name = f"load{int(time.time()) % 100000}_{i}"
        r = await timed(c, "POST", "/api/register", json={"username": name, "password": "Passw0rd!x", "code": EVENT_CODE})
        if r.status_code != 200:
            errors.append(("register", r.status_code, r.text[:80]))
            return
        await timed(c, "GET", "/api/challenges")
        ids = list(FLAGS)
        random.shuffle(ids)
        for cid in ids[: random.randint(3, 8)]:
            if random.random() < 0.5:
                r = await timed(c, "POST", f"/api/challenges/{cid}/submit", json={"flag": "FLAG{wrong}"})
                if r.status_code not in (200, 429):
                    errors.append(("wrong", r.status_code, r.text[:80]))
            r = await timed(c, "POST", f"/api/challenges/{cid}/submit", json={"flag": FLAGS[cid]})
            if r.status_code != 200 or r.json().get("status") not in ("correct", "already_solved"):
                errors.append(("correct", r.status_code, r.text[:80]))
            await timed(c, "GET", "/api/scoreboard")
        await timed(c, "GET", "/api/me")


async def main():
    start = asyncio.Event()
    tasks = [asyncio.create_task(player(i, start)) for i in range(USERS)]
    await asyncio.sleep(1)
    t0 = time.perf_counter()
    start.set()
    await asyncio.gather(*tasks)
    total = time.perf_counter() - t0
    lat.sort()
    print(f"users={USERS} requests={len(lat)} errors={len(errors)} total={total:.1f}s")
    print(f"p50={statistics.median(lat)*1000:.0f}ms p95={lat[int(len(lat)*0.95)]*1000:.0f}ms max={lat[-1]*1000:.0f}ms")
    for e in errors[:10]:
        print(e)
    async with httpx.AsyncClient(base_url=BASE) as c:
        r = await c.post("/api/login", json={"username": os.environ.get("ADMIN_USERNAME", "organiser"), "password": os.environ.get("ADMIN_PASSWORD", "")}, headers={"X-FD": "1"})
        if r.status_code == 200:
            s = (await c.get("/api/admin/summary")).json()
            print("summary", s)


asyncio.run(main())
