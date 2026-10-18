"""Sticky OpenAI-compatible router over several vLLM replicas.

Requests are routed by a hash of the conversation's opening (system prompt + first user
message), so every call in one agent session lands on the same replica and vLLM prefix
caching keeps working. Everything else (/v1/models, health) goes to the first replica.

    python serve/router.py --port 9000 --backends http://localhost:8000 http://localhost:8001
"""

import argparse
import hashlib
import json

from aiohttp import ClientSession, ClientTimeout, web

HOP_HEADERS = {"host", "content-length", "transfer-encoding", "connection"}


def route_key(body: bytes) -> str:
    try:
        data = json.loads(body)
    except Exception:
        return ""
    msgs = data.get("messages") or data.get("input") or []
    head = []
    for m in msgs if isinstance(msgs, list) else []:
        if isinstance(m, dict) and m.get("role") in ("system", "developer", "user"):
            head.append(json.dumps(m.get("content"), sort_keys=True)[:4000])
        if len(head) >= 2:
            break
    return "|".join(head)


def make_app(backends: list[str]) -> web.Application:
    app = web.Application(client_max_size=1024**3)
    session_holder: dict[str, ClientSession] = {}

    async def on_startup(app):
        session_holder["s"] = ClientSession(timeout=ClientTimeout(total=None, sock_read=3600))

    async def on_cleanup(app):
        await session_holder["s"].close()

    async def proxy(request: web.Request) -> web.StreamResponse:
        body = await request.read()
        key = route_key(body) if request.method == "POST" else ""
        idx = int(hashlib.md5(key.encode()).hexdigest(), 16) % len(backends) if key else 0
        url = backends[idx] + request.rel_url.path_qs
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS}
        async with session_holder["s"].request(request.method, url, data=body, headers=headers) as r:
            resp = web.StreamResponse(status=r.status, headers={
                k: v for k, v in r.headers.items() if k.lower() not in HOP_HEADERS})
            resp.headers["X-Router-Backend"] = str(idx)
            await resp.prepare(request)
            async for chunk in r.content.iter_any():
                await resp.write(chunk)
            await resp.write_eof()
            return resp

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_route("*", "/{tail:.*}", proxy)
    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--backends", nargs="+", required=True)
    a = ap.parse_args()
    web.run_app(make_app([b.rstrip("/") for b in a.backends]), port=a.port)
