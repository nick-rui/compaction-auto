"""Thin async client for the vLLM OpenAI-compatible server (Qwen3-32B)."""

import asyncio
import hashlib
import json
import os

import openai
from openai import AsyncOpenAI

# One or more identical replicas (same model + vLLM version). CA_BASE_URLS="url1,url2".
BASE_URLS = os.environ.get("CA_BASE_URLS", os.environ.get("CA_BASE_URL", "http://127.0.0.1:18000/v1")).split(",")
BASE_URL = BASE_URLS[0]
MODEL = os.environ.get("CA_MODEL", "qwen3-32b")

_clients = {}


def client(url=None):
    url = url or BASE_URL
    if url not in _clients:
        _clients[url] = AsyncOpenAI(base_url=url, api_key="x", timeout=1800, max_retries=2)
    return _clients[url]


def _route(messages):
    """Same conversation prefix -> same replica (keeps vLLM prefix caching useful)."""
    head = json.dumps(messages[:2], sort_keys=True)[:4000]
    return int(hashlib.md5(head.encode()).hexdigest(), 16) % len(BASE_URLS)


# Qwen3 recommended sampling (non-thinking / thinking).
SAMPLING = {
    False: dict(temperature=0.7, top_p=0.8, extra_body={"top_k": 20}),
    True: dict(temperature=0.6, top_p=0.95, extra_body={"top_k": 20}),
}


async def chat(messages, tools=None, think=False, max_tokens=4096, n=1,
               temperature=None, seed=None, **kw):
    """Returns a list of n dicts: {content, reasoning, tool_calls, finish_reason}."""
    s = {**SAMPLING[think]}
    extra = {**s.pop("extra_body"), "chat_template_kwargs": {"enable_thinking": think}}
    if temperature is not None:
        s["temperature"] = temperature
    args = dict(model=MODEL, messages=messages, max_tokens=max_tokens, n=n,
                extra_body=extra, **s, **kw)
    if tools:
        args["tools"] = tools
    if seed is not None:
        args["seed"] = seed
    # GPUs are time-shared with activation jobs: fail over between replicas and wait out
    # downtime (up to ~2h).
    i0 = _route(messages)
    for attempt in range(480):
        url = BASE_URLS[(i0 + attempt) % len(BASE_URLS)]
        try:
            r = await client(url).chat.completions.create(**args)
            break
        except (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError):
            if attempt == 479:
                raise
            if (attempt + 1) % len(BASE_URLS) == 0:
                await asyncio.sleep(15)
    out = []
    for c in r.choices:
        m = c.message
        tcs = []
        for tc in m.tool_calls or []:
            try:
                a = json.loads(tc.function.arguments)
            except Exception:
                a = tc.function.arguments
            tcs.append({"name": tc.function.name, "arguments": a})
        out.append({
            "content": m.content or "",
            "reasoning": getattr(m, "reasoning_content", None) or getattr(m, "reasoning", None),
            "tool_calls": tcs,
            "finish_reason": c.finish_reason,
        })
    return out


async def gather(coros, concurrency=48):
    sem = asyncio.Semaphore(concurrency)

    async def one(c):
        async with sem:
            return await c

    return await asyncio.gather(*[one(c) for c in coros])


def run(coros, concurrency=48):
    return asyncio.run(gather(coros, concurrency))


def assistant_msg(choice):
    """Convert a chat() choice back into an OpenAI-format assistant message."""
    m = {"role": "assistant", "content": choice["content"]}
    if choice["tool_calls"]:
        m["tool_calls"] = [
            {"id": f"call_{i}", "type": "function",
             "function": {"name": t["name"],
                          "arguments": t["arguments"] if isinstance(t["arguments"], str)
                          else json.dumps(t["arguments"])}}
            for i, t in enumerate(choice["tool_calls"])
        ]
    return m
