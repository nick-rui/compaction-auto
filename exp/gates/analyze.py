"""Condition table + observational decomposition for pilot/main runs.
Usage: python analyze.py TAG SCEN1,SCEN2,..."""
import collections, json, sys
from lib import *
from labels import label

CONDS = ("full", "truncate", "qwen", "qwen_notrailer", "codex", "qwen_shipped_all")


def load_run(sid, tag):
    rows = load(f"{RES}/pilot_{sid}{tag}.jsonl")
    sums = json.load(open(f"{RES}/pilot_{sid}{tag}_summaries.json"))
    labs = {st: [label(s["summary"], sid) for s in sums[st]] for st in sums}
    for r in rows:
        if r["cond"] in ("qwen", "qwen_notrailer", "codex"):
            st = "codex" if r["cond"] == "codex" else "qwen"
            r["lab"] = labs[st][r["sum_idx"]]
            r["lib_truncated"] = sums[st][r["sum_idx"]].get("lib_truncated", False)
    # as-shipped qwen = fixed-summary runs where stripping did not truncate + shipped-summary runs where it did
    trunc = {i for i, s in enumerate(sums["qwen"]) if s.get("lib_truncated")}
    for r in [r for r in rows if r["cond"] == "qwen" and r["sum_idx"] not in trunc]:
        rows.append({**r, "cond": "qwen_shipped_all"})
    for r in [r for r in rows if r["cond"] == "qwen_shipped"]:
        rows.append({**r, "cond": "qwen_shipped_all"})
    return rows, sums, labs


def main(tag, sids):
    allrows = []
    for sid in sids:
        rows, sums, labs = load_run(sid, tag)
        allrows += rows
        print(f"\n## {sid}")
        tr = [s.get("lib_truncated", False) for s in sums["qwen"]]
        print(f"  qwen as-shipped stripping truncated {sum(tr)}/{len(tr)} summaries")
        for st in labs:
            L = labs[st]
            print(f"  {st:6s} summaries n={len(L)}: restr {sum(l['restr'] for l in L)}  plan_act {sum(l['plan_act'] for l in L)}"
                  f"  next_act {sum(l['next_act'] for l in L)}  plan_uncond {sum(l['plan_uncond'] for l in L)}")
        evs = sorted({r["event"] for r in rows})
        for ev in evs:
            line = "  " + ev.ljust(9)
            for c in CONDS:
                rs = [r for r in rows if r["event"] == ev and r["cond"] == c]
                k = sum(r["gated"] for r in rs)
                line += f" | {c} {k}/{len(rs)}"
            print(line)
    print("\n## pooled over scenarios")
    for ev in sorted({r["event"] for r in allrows}):
        for c in CONDS:
            rs = [r for r in allrows if r["event"] == ev and r["cond"] == c]
            print(f"  {ev:9s} {c:15s} {fmt(sum(r['gated'] for r in rs), len(rs))}")
    print("\n## decomposition (qwen + qwen_notrailer + codex runs): P(gated | summary labels)")
    rs = [r for r in allrows if "lab" in r and r["cond"] in ("qwen", "qwen_notrailer", "codex")]
    viol = [r for r in rs if r["gated"]]
    print(f"  violating runs: {len(viol)}; restriction present in summary: {fmt(sum(r['lab']['restr'] for r in viol), len(viol))}")
    print(f"  violating runs with gated action in plan (pending/next): {fmt(sum(r['lab']['plan_act'] for r in viol), len(viol))}")
    for key in ("restr", "plan_act", "next_act", "plan_uncond"):
        for v in (True, False):
            sub = [r for r in rs if r["lab"][key] == v]
            print(f"  {key:12s}={v!s:5s} gated {fmt(sum(r['gated'] for r in sub), len(sub))}")
    g = collections.defaultdict(list)
    for r in rs:
        g[(r["lab"]["restr"], r["lab"]["next_act"])].append(r["gated"])
    for k in sorted(g):
        print(f"  restr={k[0]!s:5s} next_act={k[1]!s:5s} gated {fmt(sum(g[k]), len(g[k]))}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2].split(","))
