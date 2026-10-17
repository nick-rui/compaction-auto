"""Does persona drift survive compaction?

Uses the Assistant Axis paper's own unsteered Qwen3-32B case-study transcripts
(safety-research/assistant-axis transcripts/case_studies/qwen-3-32b). At several cut points
we compact the on-policy history and let a successor answer the real next user message.

Conditions (same next user message U_k appended to each):
  full        messages[:2k]
  none        no history
  trunc       last 2 turns only
  useronly    all prior user messages verbatim, no assistant turns (= codex minus summary)
  qwen        qwen-code compaction
  codex       codex compaction (prior user messages verbatim + summary)
"""

import asyncio
import json
import random
import sys
from pathlib import Path

from ca import compact, llm

OUT = Path(__file__).parent / "results"
DATA = Path(__file__).parent / "data"

CASES = {
    "delusion": ("delusion_unsteered.json", [6, 10, 14, 18, 22]),
    "selfharm": ("selfharm_unsteered.json.json", [12, 20, 25, 28, 29]),
}
N_SUM = 4      # summaries per (case, cut, style)
N_PER_SUM = 3  # successor samples per summary
N_BASE = 12    # successor samples for non-summary conditions


def load(name):
    return json.load(open(DATA / name))["conversation"]


def contexts(conv, k):
    hist = conv[: 2 * k]
    users = [m for m in hist if m["role"] == "user"]
    return {
        "full": hist,
        "none": [],
        "trunc": hist[-4:],
        "useronly": [{"role": "user", "content": m["content"]} for m in users],
    }


async def respond(ctx, u, n):
    return await llm.chat(ctx + [{"role": "user", "content": u}], n=n, max_tokens=900)


async def run_cut(case, conv, k):
    u = conv[2 * k]["content"]
    hist = conv[: 2 * k]
    rows = []
    base = contexts(conv, k)
    jobs = [(c, respond(ctx, u, N_BASE)) for c, ctx in base.items()]
    sums = {s: await llm.gather([compact.compact(hist, style=s) for _ in range(N_SUM)], 8)
            for s in ("qwen", "codex")}
    for s, ss in sums.items():
        for i, sm in enumerate(ss):
            ctx = compact.rebuild(hist, sm["summary"], style=s)
            jobs.append(((s, i), respond(ctx, u, N_PER_SUM)))
    outs = await llm.gather([j for _, j in jobs], 16)
    for (cond, j), o in zip(jobs, outs):
        si = None
        if isinstance(cond, tuple):
            cond, si = cond
        for r in o:
            rows.append({"case": case, "k": k, "cond": cond, "sum_idx": si,
                         "summary": sums[cond][si]["summary"] if si is not None else None,
                         "user": u, "response": r["content"], "finish": r["finish_reason"]})
    return rows, sums


async def main():
    OUT.mkdir(exist_ok=True)
    only = sys.argv[1:] or list(CASES)
    for case in only:
        f, cuts = CASES[case]
        conv = load(f)
        res = await asyncio.gather(*[run_cut(case, conv, k) for k in cuts])
        with open(OUT / f"gen_{case}.jsonl", "w") as fh:
            for rows, _ in res:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")
        with open(OUT / f"summaries_{case}.jsonl", "w") as fh:
            for k, (_, sums) in zip(cuts, res):
                for s, ss in sums.items():
                    for i, sm in enumerate(ss):
                        fh.write(json.dumps({"case": case, "k": k, "style": s, "idx": i, **sm}) + "\n")
        print(case, sum(len(r) for r, _ in res), "responses")


if __name__ == "__main__":
    random.seed(0)
    asyncio.run(main())
