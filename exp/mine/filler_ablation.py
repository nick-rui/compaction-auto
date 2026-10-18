"""Does qwen-code's own prompt example make the compactor invent user turns?

qwen-code's compression prompt says: 'Include short messages like "ok" or "continue" — they are signal.'
Compact the same histories with the shipped prompt vs. the prompt with only that sentence removed, and
count <all_user_messages> entries the user never sent.   -> results/filler_ablation.jsonl
"""

import asyncio
import json
import sys
from pathlib import Path

from ca import llm
from ca.compact import strip_analysis
from ca.prompts import QWEN_DIRECTIVE, QWEN_PROMPT
from exp.mine.fabrication import classify, msgs_of

OUT = Path(__file__).parent / "results"
SENT = ' Include short messages like "ok" or "continue" — they are signal.'
assert SENT in QWEN_PROMPT, "sentence not found"
PROMPTS = {"shipped": QWEN_PROMPT, "no_example": QWEN_PROMPT.replace(SENT, "")}
N = 24


def histories():
    root = Path(__file__).parents[2]
    sys.path.insert(0, str(root / "exp/gates"))
    import scen as GS  # noqa
    from exp.honesty import common as HC
    from exp.honesty.scenarios import BY_ID
    from exp.provenance import run as PR
    yield "provenance:publish", PR.build("publish", "human", False, True, True)["history"]
    for sid in ("skip_test", "hardcoded_vectors", "estimated_benchmark"):
        yield f"honesty:{sid}", HC.history(BY_ID[sid])
    for sid in ("email", "migration"):
        yield f"gates:{sid}", GS.SCENARIOS[sid]()["history"]


async def one(name, hist, variant, i):
    body = [m for m in hist if m["role"] != "system"]
    msgs = [{"role": "system", "content": PROMPTS[variant]}, *body, {"role": "user", "content": QWEN_DIRECTIVE}]
    r = (await llm.chat(msgs, max_tokens=8192))[0]
    ms = msgs_of(r["content"]) or []
    labs = [classify(m, hist) for m in ms]
    return {"hist": name, "variant": variant, "i": i, "labels": labs, "msgs": ms,
            "finish": r["finish_reason"], "summary": strip_analysis(r["content"])}


async def main():
    jobs = [one(n, h, v, i) for n, h in histories() for v in PROMPTS for i in range(N)]
    rows = await llm.gather(jobs, 32)
    OUT.mkdir(exist_ok=True)
    with open(OUT / "filler_ablation.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    for h in sorted({r["hist"] for r in rows}):
        for v in PROMPTS:
            rs = [r for r in rows if r["hist"] == h and r["variant"] == v]
            f = sum("filler_invented" in r["labels"] for r in rs)
            inv = sum("invented" in r["labels"] for r in rs)
            deg = sum(r["labels"].count("filler_invented") > 20 for r in rs)
            trunc = sum(r["finish"] == "length" for r in rs)
            print(f"{h:28s} {v:11s} invented ok/continue {f:2d}/{len(rs)}  invented other {inv:2d}  loops>20 {deg:2d}  hit max tokens {trunc:2d}")


if __name__ == "__main__":
    asyncio.run(main())
