"""Exp 2: agent-memory feedback loop. Does compaction amplify an adversarial interpretation?

Chain: X_0 = H0(seed). For t=1..T: X += obs_t; note_t = agent(X) (on-policy); X += note_t;
       [compacted dyn: X = rebuild(compact(X))]; probe(X).
dyn: full (never compact), qwen, qwen_hp (hedge-preserving compactor),
     pure (qwen compaction, but scripted CI chores instead of observations -> no new evidence,
           no agent interpretations).
Probes per round: belief JSON (n=3) and one-step action probe with tools (n=2).

usage: python -m exp.ratchet.run_feedback --dyn qwen full --seed adv mun --n 30 --T 6
"""

import argparse
import asyncio
import re
import time

from ca import llm
from exp.ratchet import ci_scenario as CI
from exp.ratchet import common as U

KEYS = ["p_transient_infra", "p_deliberate_interference", "p_misconfiguration", "p_other"]


async def belief(ctx, n=3, think=False):
    outs = await llm.chat(ctx + [CI.PROBE], n=n, think=think, max_tokens=6000 if think else 300)
    res = []
    for o in outs:
        j = U.parse_json(o["content"]) or {}
        d = {"raw": o["content"], "most_likely": str(j.get("most_likely_cause", ""))}
        for k in KEYS:
            try:
                d[k] = float(j.get(k))
            except Exception:
                d[k] = None
        res.append(d)
    return res


async def action(ctx, think=False):
    o = (await llm.chat(ctx + [CI.ACT], tools=CI.TOOLS, think=think, max_tokens=6000 if think else 1200))[0]
    return {"content": o["content"], "tool_calls": o["tool_calls"]}


NA = 1  # action-probe samples per round (compute budget)


async def probes(ctx, think=False):
    b, *a = await asyncio.gather(belief(ctx, think=think), *[action(ctx, think=think) for _ in range(NA)])
    return {"belief": b, "action": a}


async def chain(dyn, seed, cid, T, out, think=False):
    try:
        await _chain(dyn, seed, cid, T, out, think)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FAILED {dyn} {seed} {cid}: {e!r}", flush=True)


def _resume(dyn, seed, cid, out):
    """Rebuild the exact chain state from a per-round partial snapshot (see posthoc_feedback.context)."""
    import json, os
    from ca import compact as C
    f = out.replace(".jsonl", ".partial") + f"/{cid}.json"
    if not os.path.exists(f):
        return None, None
    rec = json.load(open(f))
    h0 = CI.history0(seed)
    t = len(rec["rounds"]) - 1
    if t == 0:
        return rec, h0
    if dyn == "full":
        X = list(h0)
        for i in range(1, t + 1):
            X += [CI.obs_msg(i - 1), {"role": "assistant", "content": rec["rounds"][i]["note"]}]
    elif dyn == "pure":
        return None, None
    else:
        X = C.rebuild(h0, rec["rounds"][t]["summary"], "qwen")
    rec.setdefault("resumed_at", t)
    return rec, X


RESUME = False


async def _chain(dyn, seed, cid, T, out, think=False):
    t0 = time.time()
    rec, X = _resume(dyn, seed, cid, out) if RESUME else (None, None)
    if rec is None:
        X = CI.history0(seed)
        rec = {"dyn": dyn, "seed": seed, "chain": cid, "think": think, "rounds": []}
        rec["rounds"].append({"t": 0, **(await probes(X, think=think))})
        U.save_partial(out, rec)
    for t in range(len(rec["rounds"]), T + 1):
        r = {"t": t}
        if dyn == "pure":
            X = X + CI.CI_CHORES[t - 1]
        else:
            X = X + [CI.obs_msg(t - 1)]
            o = (await llm.chat(X, think=think, max_tokens=6000 if think else 500))[0]
            r["note"] = o["content"]
            X = X + [{"role": "assistant", "content": o["content"]}]
        if dyn != "full":
            s, X = await U.do_compact("qwen" if dyn == "pure" else dyn, X)  # compactor never thinks
            r["summary"], r["raw"], r["truncated"] = s["summary"], s["raw"], s.get("truncated")
        r.update(await probes(X, think=think))
        rec["rounds"].append(r)
        U.save_partial(out, rec)
        print(f"  {dyn} {seed} chain {cid} round {t} ({time.time()-t0:.0f}s)", flush=True)
    rec["secs"] = time.time() - t0
    U.append_jsonl(out, rec)
    print(f"done {dyn} {seed} chain {cid} in {rec['secs']:.0f}s", flush=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dyn", nargs="+", default=["qwen"])
    ap.add_argument("--seed", nargs="+", default=["adv", "mun"])
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--T", type=int, default=6)
    ap.add_argument("--think", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    global RESUME
    RESUME = a.resume
    jobs = []
    for dyn in a.dyn:
        for seed in a.seed:
            out = f"exp/ratchet/results/feedback_{dyn}{'_think' if a.think else ''}_{seed}{a.tag}.jsonl"
            jobs += [chain(dyn, seed, i, a.T, out, think=a.think) for i in range(a.start, a.start + a.n)]
    await asyncio.gather(*jobs)


if __name__ == "__main__":
    asyncio.run(main())
