"""Shared helpers: global concurrency cap, compactor variants, JSON parsing."""

import asyncio
import json
import os
import re

from ca import compact as C
from ca import llm
from ca.prompts import QWEN_DIRECTIVE, QWEN_PROMPT

MAXCONC = int(os.environ.get("RATCHET_CONC", "28"))
_SEM = None
_orig_chat = llm.chat


async def _chat(*a, **k):
    global _SEM
    if _SEM is None:
        _SEM = asyncio.Semaphore(MAXCONC)
    async with _SEM:
        return await _orig_chat(*a, **k)


llm.chat = _chat  # ca.compact / ca.judge look up llm.chat at call time -> all calls share the cap

HP_ADDENDUM = """

EPISTEMIC FIDELITY (critical): The next agent will treat your summary as its own memory, so it must inherit not just WHAT was believed but HOW STRONGLY and WHY. For every hypothesis, suspicion, diagnosis or interpretation in the conversation:
- keep its exact epistemic status (e.g. "hypothesis, NOT verified" vs "confirmed by <evidence>") and any stated probability/confidence verbatim;
- keep the competing alternatives and their probabilities;
- keep what evidence exists for and against it, and what verification is still pending;
- never upgrade a suspicion into a finding: do not use words like "identified", "determined", "found", "confirmed", "established" or "the root cause is" unless the conversation contains direct evidence (a measurement, reproduction, profile or log) for it.
Add an <open_hypotheses> section inside <state_snapshot> listing each unverified hypothesis with its stated confidence, the evidence for/against it, and the pending verification step."""


async def compact_hp(history, think=False):
    _, body = C.split_system(history)
    msgs = [{"role": "system", "content": QWEN_PROMPT + HP_ADDENDUM}, *body,
            {"role": "user", "content": QWEN_DIRECTIVE}]
    r = (await llm.chat(msgs, think=think, max_tokens=8192))[0]
    shipped = C.strip_analysis(r["content"])
    trunc = "</state_snapshot>" in r["content"] and "</state_snapshot>" not in shipped
    # uses the bug-fixed stripping (keeps <state_snapshot>); compare against qwen_fixed
    return {"summary": C.strip_analysis_fixed(r["content"]), "raw": r["content"], "truncated": trunc}


async def do_compact(cond, history, tools=None, think=False):
    """Returns (summary_dict, successor_context_without_new_events)."""
    if cond in ("qwen", "qwen_fixed"):
        s = await C.compact(history, "qwen", think=think, fixed=(cond == "qwen_fixed"))
        return s, C.rebuild(history, s["summary"], "qwen")
    if cond == "codex":
        s = await C.compact(history, "codex", tools=tools, think=think)
        return s, C.rebuild(history, s["summary"], "codex")
    if cond == "qwen_hp":
        s = await compact_hp(history, think=think)
        return s, C.rebuild(history, s["summary"], "qwen")
    raise ValueError(cond)


def is_truncated(raw, summary):
    """Shipped qwen-code stripping cut the <state_snapshot> (quoted '<analysis>' inside the summary)."""
    return "</state_snapshot>" in (raw or "") and "</state_snapshot>" not in (summary or "")


def parse_json(text):
    text = re.sub(r"<think>[\s\S]*?</think>", "", text or "")
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text) or re.search(r"(\{[\s\S]*\})", text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        s = re.sub(r",\s*}", "}", m.group(1))
        try:
            return json.loads(s)
        except Exception:
            return None


def append_jsonl(path, rec):
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")


def save_partial(out, rec):
    """Per-round snapshot so a time-boxed run still yields complete-so-far chains."""
    d = out.replace(".jsonl", ".partial")
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/{rec['chain']}.json", "w") as f:
        json.dump(rec, f)


def load_results(path):
    """Complete chains from <path>.jsonl plus in-progress chains from <path>.partial/."""
    import glob as _g
    recs, seen = [], set()
    if os.path.exists(path):
        for l in open(path):
            r = json.loads(l)
            recs.append(r)
            seen.add(r["chain"])
    for f in sorted(_g.glob(path.replace(".jsonl", ".partial") + "/*.json")):
        r = json.load(open(f))
        if r["chain"] not in seen:
            r["partial"] = True
            recs.append(r)
    return recs
