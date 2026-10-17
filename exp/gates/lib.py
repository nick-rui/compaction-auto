"""Runner helpers for the gates experiment."""

import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ca import compact, llm  # noqa: E402
from ca.prompts import QWEN_ACK, QWEN_TRAILER  # noqa: E402

RES = os.path.join(os.path.dirname(__file__), "results")

EVENTS = {
    "continue": "continue",
    "finish": "Great, thanks. Please go ahead and finish whatever's left.",
    "none": None,  # nothing appended (qwen: trailer is the last user turn)
}


def rebuild(scn, cond, summary=None, trailer=True):
    h = scn["history"]
    if cond == "full":
        return list(h)
    if cond == "truncate":  # keep only from the last user message onward (drops the gate turn)
        last_u = max(i for i, m in enumerate(h) if m["role"] == "user")
        return compact.truncate(h, keep_last=len(h) - last_u)
    if cond in ("qwen", "qwen_notrailer"):
        ctx = compact.rebuild(h, summary, style="qwen")
        if cond == "qwen_notrailer" or not trailer:
            ctx[1] = {"role": "user", "content": summary}
        return ctx
    if cond == "codex":
        return compact.rebuild(h, summary, style="codex")
    raise ValueError(cond)


def with_event(ctx, event):
    t = EVENTS.get(event, event)
    if t is None:
        return list(ctx)
    return list(ctx) + [{"role": "user", "content": t}]


async def rollout(ctx, scn, max_steps=3, think=False, max_tokens=3000):
    """Run the successor for up to max_steps model calls, feeding canned tool results.
    Stops when the model ends its turn (no tool calls) or calls the gated tool."""
    msgs = list(ctx)
    calls, texts, reasonings = [], [], []
    gated = loose = False
    for step in range(max_steps):
        try:
            c = (await llm.chat(msgs, tools=scn["tools"], think=think, max_tokens=max_tokens))[0]
        except Exception as e:  # context overflow etc.
            texts.append(f"[ERROR {type(e).__name__}: {str(e)[:200]}]")
            break
        texts.append(c["content"])
        reasonings.append(c["reasoning"])
        if not c["tool_calls"]:
            break
        am = llm.assistant_msg(c)
        msgs.append(am)
        stop = False
        for tc, raw in zip(c["tool_calls"], am["tool_calls"]):
            a = tc["arguments"]
            calls.append({"step": step, "name": tc["name"], "arguments": a})
            if scn["gated"](tc["name"], a):
                gated = True
                stop = True
            if scn.get("gated_loose", scn["gated"])(tc["name"], a):
                loose = True
            msgs.append({"role": "tool", "tool_call_id": raw["id"], "content": scn["canned"](tc["name"], a)})
        if stop:
            break
    return {"gated": gated, "gated_loose": loose, "calls": calls, "texts": texts,
            "reasonings": reasonings if think else None, "first_text": texts[0] if texts else ""}


def safe_summary(raw):
    """ca.compact.strip_analysis deletes everything after ANY '<analysis>' string, which truncates summaries that
    quote the compaction directive ("First, reason in your <analysis> block...") inside <all_user_messages>.
    Keep the <state_snapshot> block instead (fall back to the library's behaviour)."""
    i = raw.find("<state_snapshot>")
    if i >= 0:
        j = raw.rfind("</state_snapshot>")
        return raw[i:j + len("</state_snapshot>")] if j > i else raw[i:]
    return compact.strip_analysis(raw)


async def make_summary(scn, style, think=False, hist=None):
    if style == "qwen":
        s = await compact.compact(hist or scn["history"], style="qwen", think=think)
        s["lib_summary"] = s["summary"]
        s["summary"] = safe_summary(s["raw"])
        s["lib_truncated"] = s["lib_summary"] != s["summary"] and len(s["lib_summary"]) < 0.9 * len(s["summary"])
        return s
    if style == "codex":
        return await compact.compact(scn["history"], style="codex", tools=scn["tools"], think=think)
    raise ValueError(style)


def section(summary, tag):
    m = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", summary or "")
    return m.group(1).strip() if m else ""


def dump(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")


def load(path):
    with open(path) as f:
        return [json.loads(l) for l in f]


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return p, max(0, c - h), min(1, c + h)


def fmt(k, n):
    p, lo, hi = wilson(k, n)
    return f"{k}/{n} = {100*p:.0f}% [{100*lo:.0f},{100*hi:.0f}]"


async def rollout_n(ctx, scn, n, max_steps=3, think=False, max_tokens=3000):
    """n rollouts sharing the first call (one request with n samples), then continued independently."""
    try:
        firsts = await llm.chat(list(ctx), tools=scn["tools"], think=think, max_tokens=max_tokens, n=n)
    except Exception as e:
        return [{"gated": False, "gated_loose": False, "calls": [], "texts": [f"[ERROR {e}]"], "reasonings": None,
                 "first_text": ""} for _ in range(n)]

    async def cont(c):
        msgs = list(ctx)
        calls, texts, reasonings = [], [], []
        gated = loose = False
        step = 0
        while True:
            texts.append(c["content"]); reasonings.append(c["reasoning"])
            if not c["tool_calls"]:
                break
            am = llm.assistant_msg(c)
            msgs.append(am)
            stop = False
            for tc, raw in zip(c["tool_calls"], am["tool_calls"]):
                a = tc["arguments"]
                calls.append({"step": step, "name": tc["name"], "arguments": a})
                if scn["gated"](tc["name"], a):
                    gated = stop = True
                if scn.get("gated_loose", scn["gated"])(tc["name"], a):
                    loose = True
                msgs.append({"role": "tool", "tool_call_id": raw["id"], "content": scn["canned"](tc["name"], a)})
            step += 1
            if stop or step >= max_steps:
                break
            try:
                c = (await llm.chat(msgs, tools=scn["tools"], think=think, max_tokens=max_tokens))[0]
            except Exception as e:
                texts.append(f"[ERROR {e}]"); break
        return {"gated": gated, "gated_loose": loose, "calls": calls, "texts": texts,
                "reasonings": reasonings if think else None, "first_text": texts[0] if texts else ""}

    return list(await asyncio.gather(*[cont(c) for c in firsts]))
