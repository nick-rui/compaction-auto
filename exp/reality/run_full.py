"""Full-history baseline: H0 + fillers 0..k (never compacted), probed n times per round.
usage: python -m exp.reality.run_full --n 30 --rounds 0,1,2,3,4,5,6 [--think] [--scen store,crm,study] [--conds ...]"""

import argparse
import asyncio
import os
import time

from exp.reality import common as K
from exp.reality import scen as SC


async def main(a):
    scns = a.scen.split(",")
    conds = a.conds.split(",")
    rounds = [int(x) for x in a.rounds.split(",")]
    out = os.path.join(K.RES, f"full{'_think' if a.think else ''}{a.tag}.jsonl")
    jobs = []

    async def one(scn, cond, k, i):
        ctx = K.full_ctx(scn, cond, k)
        dec = K.probe_decision(ctx, scn, think=True) if i < a.ndec else asyncio.sleep(0, result=None)
        b, d = await asyncio.gather(K.probe_belief(ctx, scn, think=a.think), dec)
        row = dict(scn=scn, cond=cond, style="full", chain=i, k=k, think=a.think, belief=b, decision=d)
        K.dump(out, [row])

    for scn in scns:
        for cond in conds:
            for k in rounds:
                for i in range(a.n):
                    jobs.append(one(scn, cond, k, i))
    t = time.time()
    await asyncio.gather(*jobs)
    print(f"done {len(jobs)} in {time.time()-t:.0f}s -> {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--rounds", default="0,1,2,3,4,5,6")
    p.add_argument("--scen", default="store,crm,study")
    p.add_argument("--conds", default=",".join(SC.CONDS))
    p.add_argument("--think", action="store_true")
    p.add_argument("--tag", default="")
    p.add_argument("--ndec", type=int, default=20, help="thinking decision probes for the first ndec samples")
    asyncio.run(main(p.parse_args()))
