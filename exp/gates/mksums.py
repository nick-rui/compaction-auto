"""Build the summary pool for the main run: reuse pilot summaries (re-extracted with safe_summary) + new ones.
Usage: python mksums.py SCEN1,.. NTOTAL OUT_TAG"""
import asyncio, json, os, sys, time
from lib import *
import scen as SC


def normalize(s, style):
    if style != "qwen" or "lib_summary" in s:
        return s
    lib = s["summary"]
    fixed = safe_summary(s["raw"])
    return {**s, "lib_summary": lib, "summary": fixed,
            "lib_truncated": lib != fixed and len(lib) < 0.9 * len(fixed)}


async def main(sids, ntot, out):
    t0 = time.time()
    pools, jobs, keys = {}, [], []
    for sid in sids:
        scn = SC.SCENARIOS[sid]()
        p = f"{RES}/pilot_{sid}_summaries.json"
        old = json.load(open(p)) if os.path.exists(p) else {"qwen": [], "codex": []}
        pools[sid] = {st: [normalize(s, st) for s in old.get(st, [])][:ntot] for st in ("qwen", "codex")}
        for st in ("qwen", "codex"):
            for _ in range(ntot - len(pools[sid][st])):
                jobs.append(make_summary(scn, st)); keys.append((sid, st))
    print(len(jobs), "new summaries", flush=True)
    res = await llm.gather(jobs, 32)
    for (sid, st), r in zip(keys, res):
        pools[sid][st].append(r)
    for sid in sids:
        json.dump(pools[sid], open(f"{RES}/pilot_{sid}{out}_summaries.json", "w"))
        tr = sum(s.get("lib_truncated", False) for s in pools[sid]["qwen"])
        print(sid, {st: len(v) for st, v in pools[sid].items()}, "shipped-truncated", tr)
    print(f"done {time.time()-t0:.0f}s")

if __name__ == "__main__":
    a = sys.argv
    asyncio.run(main(a[1].split(","), int(a[2]), a[3]))
