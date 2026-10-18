"""Repeated compaction of a long agent history with 9 planted fact types; probes at chosen rounds.

Chain (ca.compact.compact_chain, fixed=True): X_0 = H + F_0;  S_k = compact(X_{k-1});  X_k = rebuild(S_k, style) + F_k.
F_k = identical routine filler (3 threads). full baseline: H + F_0..F_k (never compacted).
Per chain we save every summary (+ raw compactor output). Probes branch off X_k (never fed back):
  knowledge: one JSON battery (all 9 facts), every round
  behavior : 4 probes (d refusal, e done, g objection, c scope), mock tools, <=4 steps

usage:
  python -m exp.halflife.run --mode chain --style claude --dom support social finance --n 12 --rounds 8 --tag main
  python -m exp.halflife.run --mode full --dom support social finance --n 12 --tag main
"""

import argparse
import asyncio
import time
import traceback

from ca import compact as C
from exp.halflife import common as U
from exp.halflife import scen as S

PROBES = ["d", "e", "g", "c"]
R = "exp/halflife/results"
CAR = "" if S.CARRIER == "natural" else f"_{S.CARRIER}"


async def probe_state(ctx, dom, k, think=False, behave=True, nb=1):
    kn = await U.knowledge(ctx, dom, think=think)
    bs = []
    if behave:
        bs = await asyncio.gather(*[U.behave(ctx, dom, p, think=think) for p in PROBES for _ in range(nb)])
    return {"k": k, "knowledge": kn, "behavior": bs}


_CSEM = None


async def chain(style, dom, seed, rounds, tag, brounds, think_probe=False, think_compact=False):
    global _CSEM
    if _CSEM is None:  # limit concurrently active chains so results stream in (same total throughput)
        import os
        _CSEM = asyncio.Semaphore(int(os.environ.get("HL_CHAINS", "14")))
    async with _CSEM:
        await _chain(style, dom, seed, rounds, tag, brounds, think_probe, think_compact)


async def _chain(style, dom, seed, rounds, tag, brounds, think_probe=False, think_compact=False):
    t0 = time.time()
    try:
        H, order = S.build_history(dom, seed)
        X0 = H + S.filler(dom, 0)
        res = await C.compact_chain(X0, rounds, style=style, between=lambda r, h: S.filler(dom, r + 1),
                                    think=think_compact)
        sums = [s["summary"] for s, _ in res]
        rec = {"style": style, "dom": dom, "seed": seed, "order": order, "think_compact": think_compact,
               "summaries": sums, "raws": [s["raw"] for s, _ in res], "truncated": [s.get("truncated") for s, _ in res],
               "regex": [U.regex_facts(dom, x) for x in sums], "secs": time.time() - t0}
        rec["carrier"] = S.CARRIER
        U.append_jsonl(f"{R}/chains_{style}{CAR}{'_tc' if think_compact else ''}_{tag}.jsonl", rec)
        print(f"chain {style} {dom} {seed} done {time.time()-t0:.0f}s", flush=True)
        jobs = []
        for k in range(1, rounds + 1):
            ctx = U.compacted_state(dom, seed, sums, k, style)
            jobs.append(probe_state(ctx, dom, k, think=think_probe, behave=(k in brounds)))
        pr = await asyncio.gather(*jobs)
        U.append_jsonl(f"{R}/probes_{style}{CAR}{'_tc' if think_compact else ''}{'_think' if think_probe else ''}_{tag}.jsonl",
                       {"style": style, "dom": dom, "seed": seed, "order": order, "rounds": pr})
        print(f"probes {style} {dom} {seed} done {time.time()-t0:.0f}s", flush=True)
    except Exception as e:
        traceback.print_exc()
        print(f"FAILED {style} {dom} {seed}: {e!r}", flush=True)


async def probe_saved(rec, tag, brounds, krounds, think_probe=False, nb=1):
    """Probe-only pass on a saved chain record (e.g. to re-probe with think=True)."""
    t0 = time.time()
    try:
        style, dom, seed, sums = rec["style"], rec["dom"], rec["seed"], rec["summaries"]
        jobs = [probe_state(U.compacted_state(dom, seed, sums, k, style), dom, k, think=think_probe,
                            behave=(k in brounds), nb=nb) for k in krounds if 1 <= k <= len(sums)]
        pr = await asyncio.gather(*jobs)
        U.append_jsonl(f"{R}/probes_{style}{'_think' if think_probe else ''}_{tag}.jsonl",
                       {"style": style, "dom": dom, "seed": seed, "order": rec["order"], "rounds": pr})
        print(f"probe_saved {style} {dom} {seed} done {time.time()-t0:.0f}s", flush=True)
    except Exception as e:
        traceback.print_exc()
        print(f"FAILED probe_saved {rec.get('dom')} {rec.get('seed')}: {e!r}", flush=True)


async def full(dom, seed, tag, brounds, krounds, think_probe=False):
    t0 = time.time()
    try:
        _, order = S.build_history(dom, seed)
        jobs = [probe_state(U.full_state(dom, seed, k), dom, k, think=think_probe, behave=(k in brounds)) for k in krounds]
        pr = await asyncio.gather(*jobs)
        U.append_jsonl(f"{R}/probes_full{CAR}{'_think' if think_probe else ''}_{tag}.jsonl",
                       {"style": "full", "dom": dom, "seed": seed, "order": order, "rounds": pr})
        print(f"full {dom} {seed} done {time.time()-t0:.0f}s", flush=True)
    except Exception as e:
        traceback.print_exc()
        print(f"FAILED full {dom} {seed}: {e!r}", flush=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="chain")
    ap.add_argument("--style", default="claude")
    ap.add_argument("--dom", nargs="+", default=S.DOMAINS)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--brounds", type=int, nargs="+", default=[2, 4, 6])
    ap.add_argument("--krounds", type=int, nargs="+", default=[0, 2, 4, 6, 8])
    ap.add_argument("--think_probe", action="store_true")
    ap.add_argument("--think_compact", action="store_true")
    ap.add_argument("--tag", default="main")
    ap.add_argument("--chains", default=None, help="probe mode: chains file to re-probe")
    ap.add_argument("--probes", nargs="+", default=None)
    a = ap.parse_args()
    if a.probes:
        PROBES[:] = a.probes
    seeds = range(a.start, a.start + a.n)
    if a.mode == "chain":
        jobs = [chain(a.style, d, s, a.rounds, a.tag, set(a.brounds), a.think_probe, a.think_compact) for s in seeds for d in a.dom]
    elif a.mode == "probe":
        recs = [r for r in U.read_jsonl(f"{R}/{a.chains}") if r["dom"] in a.dom and r["seed"] in seeds]
        jobs = [probe_saved(r, a.tag, set(a.brounds), a.krounds, a.think_probe) for r in recs]
    else:
        jobs = [full(d, s, a.tag, set(a.brounds), a.krounds, a.think_probe) for s in seeds for d in a.dom]
    await asyncio.gather(*jobs)


if __name__ == "__main__":
    asyncio.run(main())
