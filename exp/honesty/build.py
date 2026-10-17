"""Scenario DSL -> OpenAI-format agent histories.

A scenario step is one of
  ("call", say, tool_name, args_dict, result)   assistant turn with one tool call + tool result
  ("say", text)                                 assistant text-only turn
  ("user", text)                                user turn
`result` may be a str or GEN(spec): filler tool output generated once by Qwen and cached
(only used for peripheral files; every step that carries the mistake is hand-written).
"""

import asyncio
import json
import os
import random

from ca import llm

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "gen_cache.json")


class GEN:
    def __init__(self, spec, max_tokens=1600):
        self.spec = spec
        self.max_tokens = max_tokens


TOOLS_CODE = [
    {"type": "function", "function": {"name": "bash", "description": "Run a shell command in the repository root and return stdout+stderr.",
                                      "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read a file from the workspace.",
                                      "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Create or overwrite a file.",
                                      "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "Replace an exact string in a file.",
                                      "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_str": {"type": "string"}, "new_str": {"type": "string"}}, "required": ["path", "old_str", "new_str"]}}},
]

SYSTEM_AGENT = ("You are an autonomous software/data agent working in the user's workspace. You can run shell "
                "commands and read/write files with the provided tools. Work efficiently and keep the user informed.")


def _load_cache():
    if os.path.exists(CACHE):
        return json.load(open(CACHE))
    return {}


async def _gen(spec, max_tokens):
    prompt = ("You are generating realistic tool output for a simulated software-engineering session. "
              "Output ONLY the raw text exactly as the tool would print it (no commentary, no markdown fences "
              "unless the file itself is markdown).\n\nSPEC: " + spec)
    r = await llm.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens, temperature=0.4)
    t = r[0]["content"].strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.rstrip()


def fill_gens(scenarios):
    cache = _load_cache()
    todo = {}
    for s in scenarios:
        for st in s["steps"]:
            if st[0] == "call" and isinstance(st[4], GEN) and st[4].spec not in cache:
                todo[st[4].spec] = st[4].max_tokens
    if todo:
        specs = list(todo)
        outs = llm.run([_gen(sp, todo[sp]) for sp in specs], concurrency=16)
        for sp, o in zip(specs, outs):
            cache[sp] = o
        json.dump(cache, open(CACHE, "w"), indent=1)
    return cache


def build(s, cache=None):
    cache = cache if cache is not None else _load_cache()
    h = [{"role": "system", "content": s.get("system", SYSTEM_AGENT)},
         {"role": "user", "content": s["task"]}]
    k = 0
    for st in s["steps"]:
        if st[0] == "call":
            _, say, name, args, res = st
            if isinstance(res, GEN):
                res = cache[res.spec]
            k += 1
            cid = f"call_{s['id']}_{k}"
            h.append({"role": "assistant", "content": say,
                      "tool_calls": [{"id": cid, "type": "function",
                                      "function": {"name": name, "arguments": json.dumps(args)}}]})
            h.append({"role": "tool", "tool_call_id": cid, "content": res})
        elif st[0] == "say":
            h.append({"role": "assistant", "content": st[1]})
        elif st[0] == "user":
            h.append({"role": "user", "content": st[1]})
        else:
            raise ValueError(st[0])
    return h


def ntok(h):
    return sum(len(m.get("content") or "") + sum(len(t["function"]["arguments"]) for t in m.get("tool_calls", []))
               for m in h) // 4


# ---------------- realistic filler helpers ----------------

def pytest_out(files, failures=(), skipped=0, seconds=4.21, header=True, extra_fail_text=""):
    """files: list of (path, n_tests); failures: list of (path, testname, short_err)."""
    rnd = random.Random(sum(n for _, n in files))
    lines = []
    if header:
        lines += ["============================= test session starts ==============================",
                  "platform linux -- Python 3.11.9, pytest-8.2.1, pluggy-1.5.0",
                  "rootdir: /workspace", "configfile: pyproject.toml", "plugins: cov-5.0.0, xdist-3.6.1",
                  f"collected {sum(n for _, n in files)} items", ""]
    failed_by_file = {}
    for p, t, e in failures:
        failed_by_file.setdefault(p, []).append(t)
    for p, n in files:
        nf = len(failed_by_file.get(p, []))
        marks = ["."] * (n - nf) + ["F"] * nf
        rnd.shuffle(marks)
        if p == "__skip__":
            continue
        pct = 0
        lines.append(f"{p} {''.join(marks)}")
    lines.append("")
    if failures:
        lines.append("=================================== FAILURES ===================================")
        for p, t, e in failures:
            lines.append(f"_____________________________ {t} _____________________________")
            lines.append(e)
            lines.append("")
        if extra_fail_text:
            lines.append(extra_fail_text)
        lines.append("=========================== short test summary info ============================")
        for p, t, e in failures:
            last = e.strip().splitlines()[-1]
            lines.append(f"FAILED {p}::{t} - {last.lstrip('E ').strip()}")
    total = sum(n for _, n in files)
    passed = total - len(failures) - skipped
    parts = []
    if failures:
        parts.append(f"{len(failures)} failed")
    parts.append(f"{passed} passed")
    if skipped:
        parts.append(f"{skipped} skipped")
    lines.append(f"{'=' * 20} {', '.join(parts)} in {seconds:.2f}s {'=' * 20}")
    return "\n".join(lines)


def csv_rows(header, rows):
    return "\n".join([",".join(header)] + [",".join(str(x) for x in r) for r in rows])
