"""Calibration for compactor projections: compact non-drift (coding, writing) and drift-domain
(therapy, philosophy) conversations from the paper's persona_drift transcripts with the same
prompts, so compactor Assistant-Axis values can be compared against a no-drift baseline.

  python -m exp.persona.control   -> results/control_summaries.jsonl
"""

import asyncio
import json
from pathlib import Path

from ca import compact, llm

R = Path(__file__).parent / "results"
D = Path(__file__).parent / "data"
DOMAINS = ["coding", "writing", "therapy", "philosophy"]
N = 4


async def one(dom, conv, k, style, i):
    s = await compact.compact(conv[: 2 * k], style=style)
    return {"domain": dom, "k": k, "style": style, "idx": i, **s}


async def main():
    jobs = []
    for dom in DOMAINS:
        conv = json.load(open(D / f"{dom}.json"))["conversation"]
        k = min(14, len(conv) // 2 - 1)
        jobs += [one(dom, conv, k, st, i) for st in ("qwen", "codex") for i in range(N)]
    rows = await llm.gather(jobs, 16)
    with open(R / "control_summaries.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
