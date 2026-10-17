"""Pilot: conditions x events for scenarios. Usage: python pilot.py SCEN1,SCEN2 NSUM NSUCC [events] [tag]"""
import asyncio, json, sys, time
from lib import *
import scen as SC

CONDS = ("full", "truncate", "qwen", "qwen_notrailer", "codex", "qwen_shipped")

async def main(sids, nsum, nsucc, events, think=False, tag=""):
    t0 = time.time()
    scns = {sid: SC.SCENARIOS[sid]() for sid in sids}
    keys = [(sid, st) for sid in sids for st in ("qwen", "codex")]
    res = await llm.gather([make_summary(scns[sid], st) for sid, st in keys for _ in range(nsum)], 32)
    sums = {}
    for idx, (sid, st) in enumerate(keys):
        sums.setdefault(sid, {})[st] = res[idx * nsum:(idx + 1) * nsum]
    print(f"summaries done {time.time()-t0:.0f}s", flush=True)
    jobs, meta = [], []
    for sid in sids:
        scn = scns[sid]
        for ev in events:
            for cond in CONDS:
                if cond in ("full", "truncate"):
                    srcs = [(None, None)] * nsum
                elif cond == "qwen_shipped":  # as-shipped stripping; only differs where it truncated
                    srcs = [(i, s["lib_summary"]) for i, s in enumerate(sums[sid]["qwen"]) if s.get("lib_truncated")]
                else:
                    st = "codex" if cond == "codex" else "qwen"
                    srcs = [(i, s["summary"]) for i, s in enumerate(sums[sid][st])]
                for si, summ in srcs:
                    ctx = with_event(rebuild(scn, "qwen" if cond == "qwen_shipped" else cond, summ), ev)
                    for j in range(nsucc):
                        jobs.append(rollout(ctx, scn, think=think))
                        meta.append(dict(scen=sid, event=ev, cond=cond, sum_idx=si, rep=j))
    outs = await llm.gather(jobs, 32)
    rows = [dict(**m, **o) for m, o in zip(meta, outs)]
    for sid in sids:
        dump(f"{RES}/pilot_{sid}{tag}.jsonl", [r for r in rows if r["scen"] == sid])
        json.dump(sums[sid], open(f"{RES}/pilot_{sid}{tag}_summaries.json", "w"))
    print(f"done {time.time()-t0:.0f}s")
    for sid in sids:
        for ev in events:
            for cond in CONDS:
                rs = [r for r in rows if r["scen"] == sid and r["event"] == ev and r["cond"] == cond]
                print(f"{sid:10s} {ev:9s} {cond:15s} gated {fmt(sum(r['gated'] for r in rs), len(rs))}")

if __name__ == "__main__":
    sids, nsum, nsucc = sys.argv[1].split(","), int(sys.argv[2]), int(sys.argv[3])
    evs = sys.argv[4].split(",") if len(sys.argv) > 4 else ["continue", "finish"]
    tag = sys.argv[5] if len(sys.argv) > 5 else ""
    asyncio.run(main(sids, nsum, nsucc, evs, tag=tag))
