"""Full history (never compacted) + Claude Code's continuation line, thinking decision.
  final: line appended to the decision user turn;  pos: line as its own user turn before the last chore (where it sits
  in compacted states);  none: control.   python -m exp.reality.full_line --n 20"""
import argparse, asyncio, os
from ca import compact as C
from exp.reality import common as K, scen as SC


async def main(a):
    out = os.path.join(K.RES, a.out)
    async def one(scn, var, i):
        ctx = K.full_ctx(scn, "REAL", 3)
        dec = SC.meta(scn)["decision"]
        if var == "final":
            dec = dec + "\n\n" + C.CLAUDE_SUFFIX
        elif var in ("pos", "cmsg"):  # own user turn / compaction-style user message, before the last chore
            j = len(ctx) - len(SC.filler(3))
            txt = C.CLAUDE_SUFFIX if var == "pos" else (
                f"{C.CLAUDE_PREFIX}\n\n(The earlier conversation is shown above in full.)\n\n{C.CLAUDE_SUFFIX}")
            ctx = ctx[:j] + [{"role": "user", "content": txt}] + ctx[j:]
        elif var == "sysnote":  # same line as an operator/system note
            ctx = [{"role": "system", "content": ctx[0]["content"] + "\n\nNote: " + C.CLAUDE_SUFFIX}] + ctx[1:]
        d = await K.probe_decision(ctx, scn, think=True, decision=dec)
        K.dump(out, [dict(scn=scn, cond="REAL", var=var, chain=i, k=3, decision=d)])
    jobs = [one(s, v, i) for i in range(a.i0, a.i0 + a.n) for v in a.vars.split(",") for s in ("store", "crm")
            if not (v == "pos" and i >= a.i0 + a.npos)]
    await asyncio.gather(*jobs)
    print("done", len(jobs))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--npos", type=int, default=10)
    p.add_argument("--vars", default="final,pos")
    p.add_argument("--out", default="full_line.jsonl")
    p.add_argument("--i0", type=int, default=0)
    asyncio.run(main(p.parse_args()))
