"""Ablation: scripted histories with the gated item removed from the agent's todo lists (everything else identical).
Usage: python notodo.py SCENS NSUM NSUCC TAG"""
import asyncio, copy, json, re, sys, time
from lib import *
import scen as SC
from labels import label, ACT


def strip_gated_todo(scn):
    s = dict(scn)
    h = copy.deepcopy(scn["history"])
    removed = 0
    for m in h:
        if m["role"] == "assistant" and m.get("tool_calls"):
            for t in m["tool_calls"]:
                if t["function"]["name"] == "todo_write":
                    a = json.loads(t["function"]["arguments"])
                    keep = [x for x in a["todos"] if not re.search(ACT[scn["id"]], x, re.I)]
                    removed += len(a["todos"]) - len(keep)
                    a["todos"] = keep
                    t["function"]["arguments"] = json.dumps(a)
    for i, m in enumerate(h):  # fix the "todo list updated (N items)" results
        if m["role"] == "tool" and m["content"].startswith("todo list updated"):
            prev = h[i - 1]["tool_calls"][0]["function"]["arguments"]
            m["content"] = f"todo list updated ({len(json.loads(prev)['todos'])} items)"
    s["history"] = h
    s["removed"] = removed
    return s


async def main(sids, nsum, nsucc, tag):
    t0 = time.time()
    scns = {sid: strip_gated_todo(SC.SCENARIOS[sid]()) for sid in sids}
    for sid in sids:
        print(sid, "removed todo items:", scns[sid]["removed"], flush=True)
    keys = [sid for sid in sids for _ in range(nsum)]
    sums = await llm.gather([make_summary(scns[k], "qwen") for k in keys], 32)
    pool = {sid: [] for sid in sids}
    for k, s in zip(keys, sums):
        pool[k].append(s)
    json.dump(pool, open(f"{RES}/notodo_{tag}_summaries.json", "w"))
    print(f"summaries done {time.time()-t0:.0f}s", flush=True)
    jobs, meta = [], []
    for sid in sids:
        scn = scns[sid]
        for cond in ("full", "qwen"):
            srcs = [(None, list(scn["history"]))] * nsum if cond == "full" else \
                [(i, rebuild(scn, "qwen", s["summary"])) for i, s in enumerate(pool[sid])]
            for si, ctx in srcs:
                jobs.append(rollout_n(with_event(ctx, "continue"), scn, nsucc))
                meta.append(dict(scen=sid, cond=cond, sum_idx=si))
    outs = await llm.gather(jobs, max(1, 32 // nsucc))
    rows = [dict(**m, rep=j, **o) for m, os_ in zip(meta, outs) for j, o in enumerate(os_)]
    dump(f"{RES}/notodo_{tag}.jsonl", rows)
    print(f"done {time.time()-t0:.0f}s")
    for sid in sids + ["ALL"]:
        print(sid.ljust(10), " | ".join(f"{c} {fmt(sum(r['gated'] for r in rows if r['cond']==c and sid in ('ALL', r['scen'])), sum(1 for r in rows if r['cond']==c and sid in ('ALL', r['scen'])))}" for c in ("full", "qwen")))
    for sid in sids:
        L = [label(s["summary"], sid) for s in pool[sid]]
        print(f"  {sid} summaries: plan_act {sum(l['plan_act'] for l in L)}/{len(L)} next_act {sum(l['next_act'] for l in L)} restr {sum(l['restr'] for l in L)}")

if __name__ == "__main__":
    a = sys.argv
    asyncio.run(main(a[1].split(","), int(a[2]), int(a[3]), a[4]))
