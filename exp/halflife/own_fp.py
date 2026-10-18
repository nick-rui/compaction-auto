"""First-person compaction prompt on the exp/ownership trajectories (reuses exp/ownership's histories, filler, episode
runner, world simulator and judges unchanged; only the compaction prompt differs).

Chain = exp/ownership make_chain with the Claude-Code-format prompt + run2.FIRST_PERSON, rebuilt with the claude framing,
FILLER between rounds. Probe = the manager's "Did you do this? Why?" at round 1 (cond fp) and round 3 (cond fp_r3).
Outputs go to exp/halflife/results/own_fp_*.jsonl (exp/ownership/results is not touched).

python -m exp.halflife.own_fp --stage summaries --k 2
python -m exp.halflife.own_fp --stage episodes --k 2
python -m exp.halflife.own_fp --stage judge
"""
import argparse
import asyncio
import os

from exp.halflife import common as HL  # noqa: F401  (load-aware routing + global cap HL_CONC)
from exp.halflife.run2 import FIRST_PERSON, compact_custom
import exp.ownership.run as O
from ca import compact as C
from exp.honesty.build import build
from exp.honesty.scenarios import ALL, BY_ID
from exp.ownership.scen import FILLER

O.RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


async def make_chain(SS, s, k, rounds=3):
    keys = [f"{s['id']}|fp|{k}|r{r + 1}" for r in range(rounds)]
    if all(x in SS for x in keys):
        return
    hist = build(s)
    for r in range(rounds):
        sd = await compact_custom(hist, FIRST_PERSON, seed=O.seed_of(s["id"], "chain", k, r))
        rebuilt = C.rebuild(hist, sd["summary"], style="claude")
        await SS.add({"key": keys[r], "scen": s["id"], "style": "fp", "k": k, "round": r + 1, "summary": sd["summary"],
                      "raw": sd["raw"], "ctx": rebuilt})
        hist = rebuilt + (FILLER[r] if r < len(FILLER) else [])


async def main(a):
    O._SEM = asyncio.Semaphore(a.conc)
    ks = range(a.k0, a.k0 + a.k)
    SS = O.Store("own_fp_summaries.jsonl")
    if a.stage == "summaries":
        sem = asyncio.Semaphore(a.conc)

        async def lim(s, k):
            async with sem:
                await make_chain(SS, s, k)
        jobs = [lim(s, k) for k in ks for s in ALL]
    elif a.stage == "episodes":
        EP = O.Store("own_fp_episodes.jsonl")
        esem = asyncio.Semaphore(a.conc)

        async def lim(s, k, rnd):
            r = SS.get(f"{s['id']}|fp|{k}|r{rnd}")
            if r is None:
                return
            async with esem:
                await O.episode(EP, s, "fp" if rnd == 1 else f"fp_r{rnd}", k, "probe", r["ctx"])
        jobs = [lim(s, k, rnd) for k in ks for rnd in (1, 3) for s in ALL]
    else:
        EP = O.Store("own_fp_episodes.jsonl")
        JE = O.Store("own_fp_judge.jsonl")
        JSm = O.Store("own_fp_judge_summaries.jsonl")
        jobs = [O.judge_ep(JE, BY_ID[r["scen"]], r) for r in EP.d.values()]
        jobs += [O.judge_sum(JSm, BY_ID[r["scen"]], r) for r in SS.d.values()]
    done = 0
    for fut in asyncio.as_completed(jobs):
        await fut
        done += 1
        if done % 10 == 0:
            print(f"{done}/{len(jobs)}", flush=True)
    print("done", len(jobs), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--stage", required=True, choices=["summaries", "episodes", "judge"])
    p.add_argument("--k", type=int, default=2)
    p.add_argument("--k0", type=int, default=0)
    p.add_argument("--conc", type=int, default=4)
    asyncio.run(main(p.parse_args()))
