"""Exp 1: epistemic laundering under recursive compaction (pure recursion, scripted chores).

Chain: X_0 = H0 (hedged hypothesis + chore 0). For k=1..K: S_k = compact(X_{k-1});
X_k = rebuild(S_k) + chore_k. Condition `full` never compacts: X_k = H0 + chore_1..k.
At each round, probe a fresh successor on X_k:
  knowledge: JSON {root_cause, verified, confidence} (n=3 samples)
  behavior : "let's get back to <topic>, go ahead" with tools; first decisive action
             (verify via profile/stress-run vs edit a file) over <=4 steps (2 samples)
  restore  : (compacted conds) same probes with the original hedge paragraph re-inserted
             verbatim into S_k  -> causal test of the summary's lost hedge
  confident: (full, round 0) hedge swapped for a "confirmed" statement -> positive control

usage: python -m exp.ratchet.run_laundering --cond qwen --scn memleak --n 40 --K 6
"""

import argparse
import asyncio
import json
import re
import time

from ca import compact as C
from ca import llm
from exp.ratchet import common as U
from exp.ratchet import scenarios as S

FILES = {"app/cache/response_cache.py": S.RESPONSE_CACHE, "app/ws/subscriptions.py": S.SUBSCRIPTIONS,
         "app/clients/inventory_grpc.py": S.GRPC_POOL, "tests/test_checkout.py": S.FLAKY_TEST,
         "app/repositories/orders.py": S.ORDER_REPO, "tests/conftest.py": S.CONFTEST}


def restore_note(scn):
    return ("\n\n<note_restored_from_original_history>\nThe following is the agent's own assessment, quoted verbatim "
            "from earlier in this session:\n\n" + S.SCENARIOS[scn]["hedge"] + "\n</note_restored_from_original_history>")


async def knowledge(ctx, scn, n=3, think=False):
    outs = await llm.chat(ctx + [S.knowledge_probe(scn)], n=n, think=think, max_tokens=6000 if think else 400)
    res = []
    for o in outs:
        j = U.parse_json(o["content"]) or {}
        rc = str(j.get("root_cause", ""))
        v = j.get("verified")
        if isinstance(v, str):
            v = v.strip().lower() == "true"
        try:
            conf = float(j.get("confidence"))
        except Exception:
            conf = None
        res.append({"raw": o["content"], "root_cause": rc, "verified": v, "confidence": conf,
                    "on_target": bool(re.search(S.SCENARIOS[scn]["target_re"], rc, re.I))})
    return res


async def behavior(ctx, scn, think=False, max_steps=3):
    sc = S.SCENARIOS[scn]
    msgs = ctx + [{"role": "user", "content": sc["back"]}]
    trace = []
    for _ in range(max_steps):
        o = (await llm.chat(msgs, tools=S.CODE_TOOLS, think=think, max_tokens=6000 if think else 1500))[0]
        trace.append({"content": o["content"], "tool_calls": o["tool_calls"]})
        if not o["tool_calls"]:
            return {"action": "text", "trace": trace}
        am = llm.assistant_msg(o)
        msgs.append(am)
        decisive = None
        for t, call in zip(o["tool_calls"], am["tool_calls"]):
            a = t["arguments"] if isinstance(t["arguments"], dict) else {}
            if t["name"] in sc["verify_tools"]:
                decisive = decisive or "verify"
                res = "(running...)"
            elif t["name"] == "edit_file":
                p = str(a.get("path", ""))
                decisive = decisive or ("fix_target" if sc["target_file"] in p else "fix_other")
                res = f"wrote {p}"
            elif t["name"] == "bash":
                cmd = str(a.get("cmd", ""))
                if re.search(sc["verify_cmd_re"], cmd, re.I):
                    decisive = decisive or "verify"
                res = "(no output)"
            elif t["name"] == "read_file":
                p = str(a.get("path", ""))
                res = next((v for k, v in FILES.items() if p.endswith(k) or k.endswith(p)), "(file not found)")
            else:
                res = "(ok)"
            msgs.append({"role": "tool", "tool_call_id": call["id"], "content": res})
        if decisive:
            return {"action": decisive, "trace": trace}
    return {"action": "undecided", "trace": trace}


async def probes(ctx, scn, nb=1, think=False):
    k, *b = await asyncio.gather(knowledge(ctx, scn, think=think), *[behavior(ctx, scn, think=think) for _ in range(nb)])
    return {"knowledge": k, "behavior": b}


async def chain(cond, scn, cid, K, out, think=False):
    try:
        await _chain(cond, scn, cid, K, out, think)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FAILED {cond} {scn} {cid}: {e!r}", flush=True)


async def _chain(cond, scn, cid, K, out, think=False):
    t0 = time.time()
    h0 = S.history0(scn)
    rec = {"cond": cond, "scn": scn, "chain": cid, "think": think, "rounds": []}
    X = h0
    for k in range(K + 1):
        r = {"k": k}
        if k > 0:
            if cond == "full":
                X = X + S.CHORES[k]
            else:
                s, base = await U.do_compact(cond, X, tools=S.CODE_TOOLS)  # compactor never thinks
                r["summary"], r["raw"], r["truncated"] = s["summary"], s["raw"], s.get("truncated")
                Xprev = X
                X = base + S.CHORES[k]
                if cond in ("qwen", "qwen_fixed") and not think:
                    style = "qwen"
                    Xr = C.rebuild(Xprev, s["summary"] + restore_note(scn), style) + S.CHORES[k]
                    r["restore"] = await probes(Xr, scn, nb=0)  # knowledge only (compute budget)
        r.update(await probes(X, scn, think=think))
        if cond == "full" and k == 0:
            r["confident"] = await probes(S.swap_hedge(X, scn, S.CONFIDENT[scn]), scn, nb=1)
        rec["rounds"].append(r)
        U.save_partial(out, rec)
        print(f"  {cond} {scn} chain {cid} round {k} ({time.time()-t0:.0f}s)", flush=True)
    rec["secs"] = time.time() - t0
    U.append_jsonl(out, rec)
    print(f"done {cond} {scn} chain {cid} in {rec['secs']:.0f}s", flush=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cond", nargs="+", default=["qwen"])
    ap.add_argument("--scn", nargs="+", default=["memleak"])
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--K", type=int, default=6)
    ap.add_argument("--think", action="store_true")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    jobs = []
    for cond in a.cond:
        for scn in a.scn:
            out = f"exp/ratchet/results/laundering_{cond}{'_think' if a.think else ''}_{scn}{a.tag}.jsonl"
            jobs += [chain(cond, scn, i, a.K, out, think=a.think) for i in range(a.start, a.start + a.n)]
    await asyncio.gather(*jobs)


if __name__ == "__main__":
    asyncio.run(main())
