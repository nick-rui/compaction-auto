"""LLM-as-judge helpers (Qwen3-32B with thinking, JSON answer)."""

import json
import re

from . import llm


def parse_json(text):
    text = re.sub(r"<think>[\s\S]*?</think>", "", text or "")
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text) or re.search(r"(\{[\s\S]*\})", text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


async def judge(prompt, think=True, max_tokens=6000, retries=2):
    """prompt should ask for a single JSON object. Returns dict or None."""
    for _ in range(retries + 1):
        r = (await llm.chat([{"role": "user", "content": prompt}], think=think,
                            max_tokens=max_tokens, temperature=0.0 if not think else None))[0]
        out = parse_json(r["content"])
        if out is not None:
            return out
    return None


def render(messages, max_chars=None):
    """Plain-text transcript for judges / humans."""
    lines = []
    for m in messages:
        role = m["role"].upper()
        c = m.get("content") or ""
        if m.get("tool_calls"):
            calls = "; ".join(f'{t["function"]["name"]}({t["function"]["arguments"]})'
                              for t in m["tool_calls"])
            c = (c + "\n" if c else "") + f"[TOOL CALLS] {calls}"
        if role == "TOOL":
            role = "TOOL RESULT"
        lines.append(f"### {role}\n{c}")
    s = "\n\n".join(lines)
    return s if max_chars is None else s[-max_chars:]
