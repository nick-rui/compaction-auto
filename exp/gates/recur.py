"""Recursive compaction: k = 1..4 rounds with unrelated filler work between rounds.
Usage: python recur.py SCEN1,SCEN2 NCHAIN NSUCC EVENT TAG"""
import asyncio, json, sys, time, copy
from lib import *
import scen as SC, fillers as F
from labels import label

async def chain(scn, style, ci, nsucc, event, rounds=4):
    out = []
    hist = list(scn["history"])
    for k in range(1, rounds + 1):
        s = await (make_summary(scn, "qwen", hist=hist) if style == "qwen" else
                   compact.compact(hist, style="codex", tools=scn["tools"]))
        ctx = compact.rebuild(hist, s["summary"], style=style)
        rs = await rollout_n(with_event(ctx, event), scn, nsucc)
        out.append(dict(scen=scn["id"], style=style, chain=ci, round=k, summary=s["summary"],
                        lib_truncated=s.get("lib_truncated"),
                        labels=label(s["summary"], scn["id"]), runs=rs))
        if k < rounds:
            h = F.H("x"); h.m = list(ctx); h.k = 100 * k
            F.DEV_FILLERS[k - 1](h)
            hist = h.m
    return out

async def full_chain(scn, nsucc, event, rounds=4):
    out = []
    hist = list(scn["history"])
    for k in range(1, rounds + 1):
        rs = await rollout_n(with_event(hist, event), scn, nsucc)
        out.append(dict(scen=scn["id"], style="full", chain=0, round=k, runs=rs))
        if k < rounds:
            h = F.H("x"); h.m = list(hist); h.k = 100 * k
            F.DEV_FILLERS[k - 1](h); hist = h.m
    return out

async def main(sids, nchain, nsucc, event, tag):
    t0 = time.time()
    sem = asyncio.Semaphore(8)  # chains in flight (each fans out nsucc rollouts)
    async def guarded(c):
        async with sem:
            return await c
    jobs = []
    for sid in sids:
        scn = SC.SCENARIOS[sid]()
        jobs.append(guarded(full_chain(scn, nsucc * 2, event)))
        for st in ("qwen", "codex"):
            for ci in range(nchain):
                jobs.append(guarded(chain(scn, st, ci, nsucc, event)))
    res = await asyncio.gather(*jobs)
    rows = [r for ch in res for r in ch]
    dump(f"{RES}/recur_{tag}.jsonl", rows)
    print(f"done {time.time()-t0:.0f}s")
    import collections
    agg = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
    for r in rows:
        a = agg[(r["scen"], r["style"], r["round"])]
        a[0] += sum(x["gated"] for x in r["runs"]); a[1] += len(r["runs"])
        if "labels" in r:
            a[2] += r["labels"]["restr"]; a[3] += r["labels"]["plan_act"]; a[4] += 1
    for k in sorted(agg):
        a = agg[k]
        print(k, "gated", fmt(a[0], a[1]), "| restr", a[2], "plan", a[3], "of", a[4])

if __name__ == "__main__":
    a = sys.argv
    asyncio.run(main(a[1].split(","), int(a[2]), int(a[3]), a[4], a[5]))
