"""Post-hoc fix for answers where the successor called a tool instead of replying: simulate the tool results
from the ground-truth history and let it continue until it replies (common.resolve_tools); overwrite the
answer record (originals kept) and re-judge.
python -m exp.honesty.force --prefix pilot [--src pilot]"""
import argparse
import asyncio

from ca import llm

from .common import Store, judge_answer, resolve_tools, successor_ctx
from .interventions import insert, line_for
from .run import PROBES
from .scenarios import BY_ID


async def main(a):
    A, JA = Store(f"{a.prefix}_answers.jsonl"), Store(f"{a.prefix}_judge2_answers.jsonl")
    S = Store(f"{a.src or a.prefix}_summaries.jsonl")
    sem = asyncio.Semaphore(a.conc)

    async def one(r):
        async with sem:
            s = BY_ID[r["scen"]]
            tag = r.get("tag", "")
            if tag:
                s = {**s, "final_q": PROBES[tag.lstrip("|")]}
            cond = r["cond"]
            style = cond.split("_")[0]
            if cond in ("full", "truncate"):
                ctx = successor_ctx(s, cond)
            else:
                summ = r.get("edited_summary") or r.get("fixed_summary") or S.get(f"{r['scen']}|{style}|{r['k']}|t{int(r['think'])}")["summary"]
                frame = cond
                if cond.endswith("_swap"):
                    frame = "codex" if style == "qwen" else "qwen"
                ctx = successor_ctx(s, frame, summary=summ)
            if r.get("forced"):   # undo the earlier tool_choice='none' attempt (it did not prevent tool calls)
                r = {**r, "answer": r["orig_answer"], "tool_calls": r["orig_tool_calls"]}
            nr = await resolve_tools(r, ctx, s)
            await A.add(nr)
            await judge_answer(JA, s, nr, force=True)

    todo = [r for r in A.d.values() if (r.get("tool_calls") or r.get("forced")) and not r.get("resolved")]
    print("forcing", len(todo))
    await asyncio.gather(*[one(r) for r in todo])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prefix", default="pilot")
    p.add_argument("--src", default=None)
    p.add_argument("--conc", type=int, default=6)
    asyncio.run(main(p.parse_args()))
