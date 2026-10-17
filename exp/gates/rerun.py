"""Re-run successors on SAVED summaries (e.g. think=True replication).
Usage: python rerun.py SCEN1,.. SRC_TAG OUT_TAG CONDS EVENTS NSUM NSUCC THINK"""
import asyncio, json, sys, time
from lib import *
import scen as SC


async def main(sids, src, out, conds, events, nsum, nsucc, think):
    t0 = time.time()
    jobs, meta = [], []
    for sid in sids:
        scn = SC.SCENARIOS[sid]()
        sums = json.load(open(f"{RES}/pilot_{sid}{src}_summaries.json"))
        for ev in events:
            for cond in conds:
                if cond in ("full", "truncate"):
                    srcs = [(None, None)] * nsum
                elif cond == "qwen_shipped":
                    srcs = [(i, s["lib_summary"]) for i, s in enumerate(sums["qwen"][:nsum]) if s.get("lib_truncated")]
                else:
                    st = "codex" if cond == "codex" else "qwen"
                    srcs = [(i, s["summary"]) for i, s in enumerate(sums[st][:nsum])]
                for si, summ in srcs:
                    ctx = with_event(rebuild(scn, "qwen" if cond == "qwen_shipped" else cond, summ), ev)
                    jobs.append(rollout_n(ctx, scn, nsucc, think=think, max_tokens=6000 if think else 3000))
                    meta.append(dict(scen=sid, event=ev, cond=cond, sum_idx=si, think=think))
    print(len(jobs), "jobs", flush=True)
    outs = await llm.gather(jobs, max(1, 32 // nsucc))
    rows = [dict(**m, rep=j, **o) for m, os_ in zip(meta, outs) for j, o in enumerate(os_)]
    dump(f"{RES}/rerun_{out}.jsonl", rows)
    print(f"done {time.time()-t0:.0f}s")
    for sid in sids:
        for ev in events:
            for cond in conds:
                rs = [r for r in rows if r["scen"] == sid and r["event"] == ev and r["cond"] == cond]
                print(f"{sid:10s} {ev:9s} {cond:15s} gated {fmt(sum(r['gated'] for r in rs), len(rs))}")
    for ev in events:
        for cond in conds:
            rs = [r for r in rows if r["event"] == ev and r["cond"] == cond]
            print(f"{'ALL':10s} {ev:9s} {cond:15s} gated {fmt(sum(r['gated'] for r in rs), len(rs))}")


if __name__ == "__main__":
    a = sys.argv
    asyncio.run(main(a[1].split(","), a[2], a[3], a[4].split(","), a[5].split(","), int(a[6]), int(a[7]), a[8] == "1"))
