"""Scale-up: many independent summaries per (case, cut, style), one successor reply each.

  python -m exp.persona.gen2
Writes results/gen2_<case>.jsonl rows {case, k, style, idx, summary, raw, user, response}
"""

import asyncio
import json
from pathlib import Path

from ca import compact, llm
from exp.persona.gen import CASES, load

R = Path(__file__).parent / "results"
N = 16


async def one(case, conv, k, style, i):
    hist, u = conv[: 2 * k], conv[2 * k]["content"]
    s = await compact.compact(hist, style=style)
    ctx = compact.rebuild(hist, s["summary"], style=style)
    r = (await llm.chat(ctx + [{"role": "user", "content": u}], max_tokens=900))[0]
    return {"case": case, "k": k, "style": style, "idx": i, **s, "user": u, "response": r["content"]}


async def main():
    for case, (f, cuts) in CASES.items():
        conv = load(f)
        jobs = [one(case, conv, k, st, i) for k in cuts for st in ("qwen", "codex") for i in range(N)]
        rows = await llm.gather(jobs, 16)
        with open(R / f"gen2_{case}.jsonl", "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        print(case, len(rows), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
