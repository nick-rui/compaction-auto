"""Cross-model check: does another model, used as compactor (and successor) on the same
on-policy Qwen transcripts, also codify the drifted persona into directives?

  CA_MODEL=gpt-oss-120b python -m exp.persona.xmodel
Writes results/xmodel_<model>_<case>.jsonl
"""

import asyncio
import json
import os
from pathlib import Path

from ca import compact, llm
from exp.persona.gen import load, CASES

R = Path(__file__).parent / "results"
CUTS = {"delusion": [14, 18, 22], "selfharm": [25, 28, 29]}
N = 8


async def one(case, conv, k, style, i):
    hist, u = conv[: 2 * k], conv[2 * k]["content"]
    s = await compact.compact(hist, style=style, max_tokens=6000)
    ctx = compact.rebuild(hist, s["summary"], style=style)
    r = (await llm.chat(ctx + [{"role": "user", "content": u}], max_tokens=3000))[0]
    return {"model": llm.MODEL, "case": case, "k": k, "style": style, "idx": i, **s, "user": u,
            "response": r["content"]}


async def main():
    for case, cuts in CUTS.items():
        conv = load(CASES[case][0])
        jobs = [one(case, conv, k, st, i) for k in cuts for st in ("qwen", "codex") for i in range(N)]
        rows = await llm.gather(jobs, 48)
        with open(R / f"xmodel_{llm.MODEL}_{case}.jsonl", "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        print(case, len(rows), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
