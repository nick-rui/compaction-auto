"""Main-run tables: conditions per scenario + pooled, as-shipped vs fixed qwen, observational decomposition.
Usage: python analyze_main.py RUN_TAG POOL_TAG"""
import collections, json, sys
from lib import *
from labels import label

ORDER = ["migration", "deploy", "email", "refund", "gitpush", "cleanup"]


def main(tag, pool):
    rows = load(f"{RES}/rerun_{tag}.jsonl")
    scens = [s for s in ORDER if any(r["scen"] == s for r in rows)]
    pools = {s: json.load(open(f"{RES}/pilot_{s}{pool}_summaries.json")) for s in scens}
    labs = {s: {st: [label(x["summary"], s) for x in pools[s][st]] for st in ("qwen", "codex")} for s in scens}
    for r in rows:
        if r["cond"] in ("qwen", "qwen_notrailer", "codex"):
            r["lab"] = labs[r["scen"]]["codex" if r["cond"] == "codex" else "qwen"][r["sum_idx"]]
    trunc = {(r["scen"], r["sum_idx"]) for r in rows if r["cond"] == "qwen_shipped"}
    for r in [r for r in rows if r["cond"] == "qwen" and (r["scen"], r["sum_idx"]) not in trunc]:
        rows.append({**r, "cond": "qwen_shipped_all"})
    for r in [r for r in rows if r["cond"] == "qwen_shipped"]:
        rows.append({**r, "cond": "qwen_shipped_all"})
    conds = ["full", "truncate", "qwen_shipped_all", "qwen", "qwen_notrailer", "codex"]
    print("| scenario | " + " | ".join(conds) + " |")
    print("|---" * (len(conds) + 1) + "|")
    for s in scens + ["POOLED"]:
        cells = []
        for c in conds:
            rs = [r for r in rows if r["cond"] == c and (s == "POOLED" or r["scen"] == s)]
            cells.append(fmt(sum(r["gated"] for r in rs), len(rs)))
        print(f"| {s} | " + " | ".join(cells) + " |")
    print("\nshipped-stripping truncation:", {s: sum(x.get("lib_truncated", False) for x in pools[s]["qwen"]) for s in scens},
          "of", {s: len(pools[s]["qwen"]) for s in scens})
    tr = [r for r in rows if r["cond"] == "qwen_shipped"]
    fx = [r for r in rows if r["cond"] == "qwen" and (r["scen"], r["sum_idx"]) in trunc]
    print(f"  on truncated summaries: shipped gated {fmt(sum(r['gated'] for r in tr), len(tr))} vs fixed {fmt(sum(r['gated'] for r in fx), len(fx))}")
    print("\nsummary labels (fixed text):")
    for s in scens:
        for st in ("qwen", "codex"):
            L = labs[s][st]
            print(f"  {s:10s} {st:6s} n={len(L)} restr {sum(l['restr'] for l in L)} plan_act {sum(l['plan_act'] for l in L)} "
                  f"next_act {sum(l['next_act'] for l in L)} plan_uncond {sum(l['plan_uncond'] for l in L)}")
    for grp, cs in [("qwen", ("qwen",)), ("codex", ("codex",)), ("qwen+codex", ("qwen", "codex"))]:
        rs = [r for r in rows if r["cond"] in cs]
        viol = [r for r in rs if r["gated"]]
        print(f"\n[{grp}] violating runs {len(viol)}/{len(rs)}: restriction present in summary {fmt(sum(r['lab']['restr'] for r in viol), len(viol))};"
              f" gated action in plan {fmt(sum(r['lab']['plan_act'] for r in viol), len(viol))}")
        g = collections.defaultdict(list)
        for r in rs:
            g[(r["lab"]["restr"], r["lab"]["plan_act"], r["lab"]["next_act"])].append(r["gated"])
        for k in sorted(g):
            print(f"   restr={k[0]!s:5s} plan_act={k[1]!s:5s} next_act={k[2]!s:5s}  gated {fmt(sum(g[k]), len(g[k]))}")
    # deploy: system-prompt gate is always in context
    rs = [r for r in rows if r["scen"] == "deploy" and r["cond"] in ("qwen", "codex")]
    print(f"\ndeploy (operator gate verbatim in system prompt in every condition): qwen+codex gated {fmt(sum(r['gated'] for r in rs), len(rs))}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
