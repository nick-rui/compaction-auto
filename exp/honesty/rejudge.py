"""(Re)judge every saved answer of a prefix with the current answer judge (v2) -> <prefix>_judge2_answers.jsonl."""
import argparse
import asyncio

from ca import llm

from .common import Store, judge_answer
from .run import PROBES
from .scenarios import BY_ID


async def main(a):
    A, JA = Store(f"{a.prefix}_answers.jsonl"), Store(f"{a.prefix}_judge2_answers.jsonl")
    jobs = []
    for r in A.d.values():
        if r["key"] in JA:
            continue
        s = BY_ID.get(r["scen"])
        if s is None:
            continue
        tag = r.get("tag", "")
        if tag:
            s = {**s, "final_q": PROBES[tag.lstrip("|")]}
        jobs.append(judge_answer(JA, s, r))
    print("to judge:", len(jobs))
    await llm.gather(jobs, concurrency=a.conc)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prefix", default="pilot")
    p.add_argument("--conc", type=int, default=8)
    asyncio.run(main(p.parse_args()))
