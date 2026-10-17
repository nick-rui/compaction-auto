"""qwen-code strip-analysis truncation check.

For every saved qwen summary whose shipped stripping truncated the <state_snapshot>, rebuild the successor
from the bug-fixed summary (ca.compact.strip_analysis_fixed on the same raw output) and re-ask. Non-truncated
summaries are identical under both strippers, so their 'qwenfix' outcome equals the 'qwen' outcome.

python -m exp.honesty.fixcheck --prefix pilot
"""
import argparse
import asyncio

from ca import compact as C

from .common import Store, get_answer, judge_answer, judge_summary, successor_ctx
from .scenarios import BY_ID


def truncated(rec):
    return "</state_snapshot>" in rec["raw"] and "</state_snapshot>" not in rec["summary"]


async def main(a):
    S = Store(f"{a.prefix}_summaries.jsonl")
    A, JA, JS = Store(f"{a.prefix}_answers.jsonl"), Store(f"{a.prefix}_judge2_answers.jsonl"), Store(f"{a.prefix}_judge_summaries.jsonl")
    sem = asyncio.Semaphore(24)

    async def lim(c):
        async with sem:
            return await c

    async def one(rec):
        s = BY_ID[rec["scen"]]
        fixed = C.strip_analysis_fixed(rec["raw"])
        ctx = successor_ctx(s, "qwenfix", summary=fixed)
        r = await lim(get_answer(A, s, "qwenfix", rec["k"], ctx, think=rec["think"], extra={"fixed_summary": fixed}))
        await lim(judge_answer(JA, s, r))
        await lim(judge_summary(JS, s, {**rec, "key": rec["key"].replace("|qwen|", "|qwenfix|"), "style": "qwenfix", "summary": fixed}))

    recs = [r for r in S.d.values() if r["style"] == "qwen"]
    tr = [r for r in recs if truncated(r)]
    print(f"qwen summaries: {len(recs)}  truncated by shipped stripper: {len(tr)} ({len(tr) / max(1, len(recs)):.1%})")
    await asyncio.gather(*[one(r) for r in tr])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prefix", default="pilot")
    asyncio.run(main(p.parse_args()))
