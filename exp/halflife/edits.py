"""Causal summary edits on saved compacted states (labeled interventions, not headline summaries).

For each saved chain and round k, for probes p in (d, e, g, c):
  asis    : re-run the behavior probe on the unedited state (fresh sample)
  restore : insert the ORIGINAL fact text (verbatim from the history) into the summary, re-run probe p
Only states whose summary lacks the fact (regex) are 'restore'-edited; we also run restore on states that kept
it (no-op-ish control) when --all is given.

usage: python -m exp.halflife.edits --chains chains_claude_main.jsonl --k 6 --nb 2
"""

import argparse
import asyncio
import time

from ca import compact as C
from exp.halflife import common as U
from exp.halflife import scen as S

R = "exp/halflife/results"


def restore_text(dom, p):
    f = S.D[dom]["facts"][p]
    if p == "d":
        body = f["src"]
    elif f["carrier"] == "tool":
        body = f.get("pre", "") + f["src"] + "\n" + f["ack"]
    else:
        body = f"{S.D[dom]['lead']}: {f['src']}"
    return ("\n<restored_from_original_history>\nQuoted verbatim from earlier in this session:\n" + body +
            "\n</restored_from_original_history>\n")


def insert(summary, text):
    if "</state_snapshot>" in summary:
        return summary.replace("</state_snapshot>", text + "</state_snapshot>")
    return summary + "\n" + text


def own_turn(dom, p):
    """The agent's own first-person statement of the fact, exactly as in the original history."""
    f = S.D[dom]["facts"][p]
    return f["src"] + " Leaving it unpublished for now." if p == "d" else f["ack"]


async def one(rec, k, p, cond, nb, style):
    dom, seed, sums = rec["dom"], rec["seed"], list(rec["summaries"])
    if cond == "restore":
        sums[k - 1] = insert(sums[k - 1], restore_text(dom, p))
    ctx = U.compacted_state(dom, seed, sums, k, style)
    if cond == "turn":  # same sentence, but as the agent's own assistant turn right after the summary
        i = next(j for j, m in enumerate(ctx) if m["role"] == "user" and C.CLAUDE_PREFIX[:40] in (m.get("content") or "")) \
            if style == "claude" else 2
        ctx = ctx[:i + 1] + [{"role": "assistant", "content": own_turn(dom, p)}] + ctx[i + 1:]
    bs = await asyncio.gather(*[U.behave(ctx, dom, p) for _ in range(nb)])
    return {"dom": dom, "seed": seed, "k": k, "probe": p, "cond": cond, "kept_regex": bool(rec["regex"][k - 1][p]),
            "behavior": bs, "violate": [b["violate"] for b in bs]}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chains", default="chains_claude_main.jsonl")
    ap.add_argument("--k", type=int, nargs="+", default=[6])
    ap.add_argument("--nb", type=int, default=2)
    ap.add_argument("--probes", nargs="+", default=["d", "e", "g", "c"])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--conds", nargs="+", default=["asis", "restore", "turn"])
    ap.add_argument("--out", default="edits_main.jsonl")
    a = ap.parse_args()
    recs = U.read_jsonl(f"{R}/{a.chains}")
    jobs = []
    for rec in recs:
        style = rec["style"]
        for k in a.k:
            if k > len(rec["summaries"]):
                continue
            for p in a.probes:
                kept = bool(rec["regex"][k - 1][p])
                if kept and not a.all:
                    continue
                jobs += [one(rec, k, p, c, a.nb, style) for c in a.conds]
    print(len(jobs), "jobs", flush=True)
    t0 = time.time()
    n = 0
    for c in asyncio.as_completed(jobs):
        r = await c
        U.append_jsonl(f"{R}/{a.out}", r)
        n += 1
        if n % 20 == 0:
            print(f"{n}/{len(jobs)} {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
