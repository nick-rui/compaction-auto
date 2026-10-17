"""Compactor x successor crossing: Qwen3-32B successor reading summaries written by
gpt-oss-120b vs by Qwen3-32B itself (same cuts, same harness framing, same judge).

  python -m exp.persona.cross     -> results/cross_<case>.jsonl (then judge_file)
"""

import asyncio
import json
from pathlib import Path

from ca import compact, llm
from exp.persona.gen import CASES, load

R = Path(__file__).parent / "results"
N = 3


async def one(conv, s, src):
    hist, u = conv[: 2 * s["k"]], conv[2 * s["k"]]["content"]
    ctx = compact.rebuild(hist, s["summary"], style=s["style"])
    rs = await llm.chat(ctx + [{"role": "user", "content": u}], n=N, max_tokens=900)
    return [{"case": s["case"], "k": s["k"], "style": s["style"], "idx": s["idx"], "compactor": src,
             "user": u, "response": r["content"]} for r in rs]


async def main():
    for case in CASES:
        conv = load(CASES[case][0])
        oss = [json.loads(l) for l in open(R / f"xmodel_gpt-oss-120b_{case}.jsonl")]
        cuts = {s["k"] for s in oss}
        qw = [json.loads(l) for l in open(R / f"summaries_{case}.jsonl")]
        qw = [s for s in qw if s["k"] in cuts]
        jobs = [one(conv, s, "gpt-oss-120b") for s in oss] + [one(conv, s, "qwen3-32b") for s in qw]
        rows = [r for rs in await llm.gather(jobs, 16) for r in rs]
        with open(R / f"cross_{case}.jsonl", "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        print(case, len(rows), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
