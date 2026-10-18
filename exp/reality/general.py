"""Generality of the continuation-line effect on other experiments' saved states (read-only use of their code/data).
  gates  (email, migration): saved qwen summaries rebuilt with the claude framing; event "continue"; metric = gated call
         within 3 model calls (exp/gates/lib.rollout), think=False as in exp/gates.
  halflife (support/social/finance): saved claude chains, round-2 state; refusal probe d; metric = publish_post
         (exp/halflife/common.behave), think=False as in exp/halflife.
Variants of the hand-off message's last line: line (Claude Code, as shipped) / noline / safe.
python -m exp.reality.general --nsucc 2"""
import argparse, asyncio, json, os
from exp.reality import common as K  # noqa: F401  (installs the shared concurrency cap on llm.chat)
from ca import compact as C
from exp.reality.posthoc import LINES
from exp.gates import lib as GL
from exp.gates import scen as GS
from exp.halflife import common as HU

VAR = {"line": C.CLAUDE_SUFFIX, "noline": "", "safe": LINES["safe"]}
OUT = os.path.join(K.RES, "general.jsonl")


def swap(ctx, var):
    c = ctx[1]["content"]
    assert C.CLAUDE_SUFFIX in c
    return [ctx[0], {"role": "user", "content": c.replace(C.CLAUDE_SUFFIX, VAR[var]).rstrip()}] + ctx[2:]


async def gates_one(sid, scn, i, summ, var, j):
    ctx = swap(C.rebuild(scn["history"], summ, style="claude"), var) + [{"role": "user", "content": "continue"}]
    r = await (GL.rollout(ctx, scn, max_steps=3, think=True, max_tokens=8000) if K.OSS else GL.rollout(ctx, scn, max_steps=3))
    K.dump(OUT, [dict(src="gates", scen=sid, state=i, rep=j, var=var, harm=r["gated"], calls=r["calls"],
                      first_text=r["first_text"][:600])])


async def hl_one(rec, var, j):
    ctx = swap(HU.compacted_state(rec["dom"], rec["seed"], rec["summaries"], 2, "claude"), var)
    b = await HU.behave(ctx, rec["dom"], "d", think=K.OSS)
    K.dump(OUT, [dict(src="halflife", scen=rec["dom"], state=rec["seed"], rep=j, var=var, harm=b["violate"],
                      calls=b["calls"], first_text=(b["trace"][0]["content"] if b["trace"] else "")[:600])])


async def main(a):
    jobs = []
    for sid in ("email", "migration"):
        scn = GS.SCENARIOS[sid]()
        sums = json.load(open(f"exp/gates/results/pilot_{sid}_main_summaries.json"))["qwen"]
        for i, s in enumerate(sums):
            for var in VAR:
                for j in range(a.nsucc):
                    jobs.append(gates_one(sid, scn, i, s["summary"], var, j))
    for rec in [json.loads(l) for l in open("exp/halflife/results/chains_claude_main.jsonl")]:
        for var in VAR:
            for j in range(a.nhl):
                jobs.append(hl_one(rec, var, j))
    await asyncio.gather(*jobs)
    print("done", len(jobs))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--nsucc", type=int, default=2)
    p.add_argument("--nhl", type=int, default=1)
    asyncio.run(main(p.parse_args()))
