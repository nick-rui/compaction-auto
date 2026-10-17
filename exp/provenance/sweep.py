"""Run several (guard, flag) configs in ONE process so total concurrency stays <= CONC.
python -m exp.provenance.sweep --configs guard,flag,gflag --scen ... --inject note --cond full,qwen,codex --n 10 --tag sel2
"""
import argparse, asyncio, time
from exp.provenance.run import gather_save, one, table

CFG = {"none": (False, False), "guard": (True, False), "flag": (False, True), "gflag": (True, True)}

async def main(a):
    jobs = []
    for c in a.configs.split(","):
        g, f = CFG[c]
        for scen in a.scen.split(","):
            for inj in a.inject.split(","):
                for cond in a.cond.split(","):
                    for i in range(a.n):
                        jobs.append(one(scen, inj, cond, i, think=a.think, flag=f, guard=g, finish=a.finish))
    t0 = time.time()
    recs = await gather_save(jobs, a.tag)
    print(f"{len(recs)} recs in {time.time()-t0:.0f}s")
    import pandas as pd
    pd.set_option("display.width", 200); pd.set_option("display.max_rows", 500)
    df = pd.DataFrame(recs)
    print(df.groupby(["scen", "inject", "guard", "flag", "finish", "cond"]).agg(n=("followed", "size"), follow=("followed", "mean"), acted=("acted", "mean")))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="guard")
    ap.add_argument("--scen", default="email")
    ap.add_argument("--inject", default="note")
    ap.add_argument("--cond", default="full,qwen,codex")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--think", action="store_true")
    ap.add_argument("--finish", action="store_true")
    ap.add_argument("--tag", required=True)
    asyncio.run(main(ap.parse_args()))
