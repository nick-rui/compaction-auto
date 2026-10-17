"""Assistant Axis projections for persona results (run on the GPU box, vLLM stopped).

  python -m exp.persona.project            # all cases found in results/
Writes results/proj_<case>.jsonl with per-row layer projections for:
  kind=traj      original transcript, every assistant turn
  kind=succ      every successor response in gen_<case>.jsonl (in its own context)
  kind=compactor every summary, measured in its compaction context (what the compactor 'is' while writing)
"""

import json
import sys
from pathlib import Path

from ca import compact
from ca.axis import Axis
from ca.prompts import CODEX_PROMPT, QWEN_DIRECTIVE, QWEN_PROMPT
from exp.persona.gen import CASES, contexts, load

R = Path(__file__).parent / "results"
MAX_PER = int(__import__("os").environ.get("MAX_PER", 4))  # successor samples measured per (k, cond, summary)


def succ_context(conv, row):
    k = row["k"]
    hist = conv[: 2 * k]
    if row["cond"] in ("qwen", "codex"):
        ctx = compact.rebuild(hist, row["summary"], style=row["cond"])
    else:
        ctx = contexts(conv, k)[row["cond"]]
    return ctx + [{"role": "user", "content": row["user"]}]


def compactor_context(conv, s):
    hist = conv[: 2 * s["k"]]
    if s["style"] == "qwen":
        return [{"role": "system", "content": QWEN_PROMPT}, *hist, {"role": "user", "content": QWEN_DIRECTIVE}]
    return [*hist, {"role": "user", "content": CODEX_PROMPT}]


def main(cases):
    ax = Axis(layers=(24, 32, 40))
    for case in cases:
        conv = load(CASES[case][0])
        out = open(R / f"proj_{case}.jsonl", "w")

        def emit(**kw):
            out.write(json.dumps(kw) + "\n")
            out.flush()

        for t in range(len(conv) // 2):
            p, n, _ = ax.project(conv[: 2 * t + 1], conv[2 * t + 1]["content"])
            emit(kind="traj", case=case, turn=t, proj=p, n_tok=n)
        for s in map(json.loads, open(R / f"summaries_{case}.jsonl")):
            p, n, _ = ax.project(compactor_context(conv, s), s["raw"])
            emit(kind="compactor", case=case, k=s["k"], style=s["style"], idx=s["idx"], proj=p, n_tok=n)
        gen = R / f"gen_{case}.jsonl"
        row_seen = {}
        for i, row in enumerate(map(json.loads, open(gen))):
            if row_seen.setdefault((row["k"], row["cond"], row["sum_idx"]), 0) >= MAX_PER:
                continue
            row_seen[(row["k"], row["cond"], row["sum_idx"])] += 1
            p, n, plen = ax.project(succ_context(conv, row), row["response"])
            emit(kind="succ", case=case, row=i, k=row["k"], cond=row["cond"], sum_idx=row["sum_idx"],
                 proj=p, n_tok=n, ctx_tok=plen)
        out.close()
        print(case, "done", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or [c for c in CASES if (R / f"gen_{c}.jsonl").exists()])
