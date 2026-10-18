"""Repeated compaction chains (mirrors ca.compact.compact_chain with fixed=True):
  X_0 = H0 + filler_0;  S_k = compact(X_{k-1});  X_k = rebuild(S_k, style) + filler_k;  probe X_k (k=1..K).
Each round: belief probe + decision probe on a fresh branch of X_k. Every summary/raw/probe saved.
usage: python -m exp.reality.run_chain --style claude --n 30 --K 6 [--scen ..] [--conds ..] [--onpolicy]"""

import argparse
import asyncio
import os
import time

from ca import compact as C
from ca import llm
from exp.reality import common as K
from exp.reality import scen as SC


async def onpolicy_h0(scn, cond):
    """EVIDENCE_OP: the agent's turn after reading the inbox (with the confused reply) is generated on-policy."""
    h = SC.build(scn, "EVIDENCE")[:-1]  # drop scripted assistant note; last msg = read_inbox tool result
    c = (await llm.chat(h, tools=SC.meta(scn)["tools"], max_tokens=1500))[0]
    # if it tries a tool call, keep only its text (we don't simulate further); fall back to a minimal text
    txt = c["content"].strip() or "Checked the inbox."
    return h + [{"role": "assistant", "content": txt}], {"op_note": txt, "op_tool_calls": c["tool_calls"]}


def pin(reb, scn):
    """PIN: re-insert a fixed world-state block into the hand-off message after every compaction."""
    block = f"<pinned_world_state>\n{SC.world_state(scn)}\n</pinned_world_state>"
    c = reb[1]["content"]
    c = c.replace(C.CLAUDE_SUFFIX, block + "\n\n" + C.CLAUDE_SUFFIX) if C.CLAUDE_SUFFIX in c else c + "\n\n" + block
    return [reb[0], {"role": "user", "content": c}] + reb[2:]


async def chain(scn, cond, style, i, Kmax, out, dec_rounds=(), think_probe=False, resume=None):
    extra = {}
    k0 = 1
    if resume is not None:  # continue a saved chain from its round-k summary
        h0 = SC.build(scn, cond)
        hist = C.rebuild(h0, resume["summary"], style=style) + SC.filler(resume["k"])
        k0 = resume["k"] + 1
    elif cond == "EVIDENCE_OP":
        h0, extra = await onpolicy_h0(scn, cond)
        hist = h0 + SC.filler(0)
    else:
        h0 = SC.build(scn, cond)
        hist = h0 + SC.filler(0)
    for k in range(k0, Kmax + 1):
        try:
            s, reb = await K.compact_once(hist, style, scn)
        except Exception as e:
            K.dump(out, [dict(scn=scn, cond=cond, style=style, chain=i, k=k, error=str(e)[:300])])
            return
        if cond == "PIN":
            reb = pin(reb, scn)
        hist = reb + SC.filler(k)
        dec = K.probe_decision(hist, scn, think=True) if k in dec_rounds else asyncio.sleep(0, result=None)
        b, d = await asyncio.gather(K.probe_belief(hist, scn, think=think_probe), dec)
        row = dict(scn=scn, cond=cond, style=style, chain=i, k=k, summary=s["summary"], raw=s["raw"],
                   truncated=s.get("truncated"), belief=b, decision=d, **({"h0_extra": extra} if k == 1 else {}))
        K.dump(out, [row])


async def main(a):
    scns = a.scen.split(",")
    # conds as COND:n (n chains); decisions (thinking) at --dec rounds, never for SIM/NONE controls
    conds = [(c.split(":")[0], int(c.split(":")[1]) if ":" in c else a.n) for c in a.conds.split(",")]
    dec = [int(x) for x in a.dec.split(",")] if a.dec else []
    out = os.path.join(K.RES, f"chain_{a.style}{a.tag}.jsonl")
    if a.resume:  # file:k -> continue those saved chains
        f, kr = a.resume.split(":")
        saved = {(r["scn"], r["cond"], r["chain"]): r for r in K.load(os.path.join(K.RES, f))
                 if r.get("k") == int(kr) and "error" not in r and r["style"] == a.style}
        jobs = [chain(scn, cond, a.style, i, a.K, out, dec_rounds=dec, resume=saved[(scn, cond, i)])
                for i in range(a.i0, a.i0 + max(n for _, n in conds)) for scn in scns for cond, n in conds
                if i < a.i0 + n and (scn, cond, i) in saved]
    else:
        jobs = [chain(scn, cond, a.style, i, a.K, out, dec_rounds=(() if cond in ("SIM", "NONE") and not a.dec_controls else dec))
                for i in range(a.i0, a.i0 + max(n for _, n in conds)) for scn in scns for cond, n in conds if i < a.i0 + n]
    t = time.time()
    await asyncio.gather(*jobs)
    print(f"done {len(jobs)} chains in {time.time()-t:.0f}s -> {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--style", default="claude")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--i0", type=int, default=0)
    p.add_argument("--K", type=int, default=6)
    p.add_argument("--scen", default="store,crm,study")
    p.add_argument("--conds", default=",".join(SC.CONDS))
    p.add_argument("--tag", default="")
    p.add_argument("--dec", default="1,2,4")
    p.add_argument("--dec_controls", action="store_true", help="also run decision probes for SIM/NONE chains")
    p.add_argument("--resume", default="", help="file.jsonl:k  continue saved chains from round k")
    asyncio.run(main(p.parse_args()))
