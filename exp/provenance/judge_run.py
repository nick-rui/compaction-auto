"""LLM-judge attribution of the injected instruction in summaries.

python -m exp.provenance.judge_run --tags dep50,pub50 --out judge1
"""

import argparse
import asyncio
import json
import os

from exp.provenance.analyze import judge_summary
from exp.provenance.run import RES, sem


async def one(r):
    async with sem():
        j = await judge_summary(r["scen"], r["summary"])
    return {"tag": r["_tag"], "scen": r["scen"], "inject": r["inject"], "guard": r.get("guard"),
            "cond": r["cond"], "i": r["i"], "followed": r["followed"], "judge": j}


async def main(a):
    recs = []
    for t in a.tags.split(","):
        for l in open(os.path.join(RES, f"{t}.jsonl")):
            r = json.loads(l)
            r["_tag"] = t
            if r.get("summary") and r["cond"] in ("qwen", "qwenfix", "codex"):
                recs.append(r)
    print(len(recs), "summaries")
    outs = await asyncio.gather(*[one(r) for r in recs])
    with open(os.path.join(RES, f"{a.out}.jsonl"), "w") as f:
        for o in outs:
            f.write(json.dumps(o) + "\n")
    import pandas as pd
    df = pd.DataFrame([{**{k: v for k, v in o.items() if k != "judge"},
                        "attr": (o["judge"] or {}).get("attribution"),
                        "directive": (o["judge"] or {}).get("directive")} for o in outs])
    print(pd.crosstab([df.scen, df.inject, df.cond], df.attr))
    print(df.groupby(["scen", "inject", "cond", "attr"]).followed.agg(["mean", "size"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", required=True)
    ap.add_argument("--out", required=True)
    asyncio.run(main(ap.parse_args()))
