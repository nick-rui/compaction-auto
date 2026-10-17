"""Which part of the summary carries the persona: what happened, or what to do next?

Each summary is split by an editor model into
  desc   description of what happened only (no guidance for the next assistant)
  dirs   only the behavioral guidance / directives for the next assistant
Successor conditions (same next user message):
  codex_orig / codex_desc / codex_dirs      codex framing (prior user msgs verbatim + prefix + text)
  qwen_orig  / qwen_desc  / qwen_dirs       qwen framing
  dirs_alone                                codex prefix + directives only, no user messages
Writes results/edits_<case>.jsonl
"""

import asyncio
import json
import sys
from pathlib import Path

from ca import compact, llm
from exp.persona.gen import CASES, load

R = Path(__file__).parent / "results"
N = 3

EDIT = """Below is a handoff summary of a conversation between a user and an AI assistant.

<summary>
{s}
</summary>

Rewrite it in two ways and return one JSON object with keys "desc" and "dirs".
- "desc": keep ONLY descriptive content about what happened in the conversation (what the user said,
  felt or believes, what the assistant said or did). Delete every instruction, recommendation,
  constraint, preference-to-honor, tone guidance, or next step addressed to whoever continues the
  conversation. Keep the original wording for whatever you keep.
- "dirs": keep ONLY those instructions / recommendations / constraints / tone guidance / next steps
  addressed to whoever continues the conversation, verbatim, as a short list. If there are none,
  use an empty string.
Return only the JSON object."""


async def split(summary):
    for _ in range(3):
        r = (await llm.chat([{"role": "user", "content": EDIT.format(s=summary)}], max_tokens=6000,
                            temperature=0.0))[0]
        from ca.judge import parse_json
        j = parse_json(r["content"])
        if j and "desc" in j and "dirs" in j:
            return j
    return None


async def run_case(case):
    conv = load(CASES[case][0])
    sums = [json.loads(l) for l in open(R / f"summaries_{case}.jsonl")]
    splits = await llm.gather([split(s["summary"]) for s in sums], 24)
    jobs, meta = [], []
    for s, sp in zip(sums, splits):
        if not sp:
            continue
        k, st = s["k"], s["style"]
        hist, u = conv[: 2 * k], conv[2 * k]["content"]
        variants = {f"{st}_orig": s["summary"], f"{st}_desc": sp["desc"], f"{st}_dirs": sp["dirs"] or "(none)"}
        for name, text in variants.items():
            ctx = compact.rebuild(hist, text, style=st)
            jobs.append(llm.chat(ctx + [{"role": "user", "content": u}], n=N, max_tokens=900))
            meta.append(dict(case=case, k=k, style=st, idx=s["idx"], cond=name, text=text, user=u))
        if st == "codex":
            ctx = compact.rebuild([], sp["dirs"] or "(none)", style="codex")
            jobs.append(llm.chat(ctx + [{"role": "user", "content": u}], n=N, max_tokens=900))
            meta.append(dict(case=case, k=k, style=st, idx=s["idx"], cond="dirs_alone", text=sp["dirs"], user=u))
    outs = await llm.gather(jobs, 24)
    with open(R / f"edits_{case}.jsonl", "w") as fh:
        for m, o in zip(meta, outs):
            for r in o:
                fh.write(json.dumps({**m, "response": r["content"]}) + "\n")
    print(case, len(meta), "contexts")


async def main(cases):
    await asyncio.gather(*[run_case(c) for c in cases])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or list(CASES)))
