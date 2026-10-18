"""Find case studies: trace one fact's wording across rounds and show what the successor did.

usage: python -m exp.halflife.cases --fact d [--tag main] [--max 4]
"""

import argparse
import re

from exp.halflife import common as U
from exp.halflife import scen as S

R = "exp/halflife/results"
PAT = {"d": {"support": r"faq|recall", "social": r"nut-free|recipe|brownie", "finance": r"terms|net-60"},
       "e": {d: r"881" for d in S.DOMAINS}, "g": {d: r"marco|ruiz" for d in S.DOMAINS},
       "b": {d: r"dana|whitfield" for d in S.DOMAINS},
       "a": {d: r"real|sandbox|staging|live|test" for d in S.DOMAINS},
       "c": {d: r"only|pilot list|beta-tasters list|onboarding list" for d in S.DOMAINS},
       "h": {"support": r"oct 24|restock|eta", "social": r"nov 2|tasting|venue", "finance": r"bank"},
       "f": {d: r"audit|compliance|brand-safety|logged" for d in S.DOMAINS},
       "i": {d: r"\.csv" for d in S.DOMAINS}}


def lines(summary, pat):
    return [l.strip() for l in summary.splitlines() if re.search(pat, l, re.I)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fact", default="d")
    ap.add_argument("--tag", default="main")
    ap.add_argument("--style", default="claude")
    ap.add_argument("--max", type=int, default=3)
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--dom", default=None)
    a = ap.parse_args()
    ch = {(c["dom"], c["seed"]): c for c in U.load_chains(f"{R}/chains_{a.style}_{a.tag}.jsonl")}
    pr = {(r["dom"], r["seed"]): r for r in U.read_jsonl(f"{R}/probes_{a.style}_{a.tag}.jsonl")}
    shown = 0
    for key, c in ch.items():
        if a.dom and c["dom"] != a.dom:
            continue
        r = pr.get(key)
        viol = None
        if r:
            for rd in r["rounds"]:
                if rd["k"] == a.k:
                    for b in rd["behavior"]:
                        if b["probe"] == a.fact:
                            viol = b
        if a.fact in "degc" and not (viol and viol["violate"]):
            continue
        print("=" * 100)
        print(f"{a.style} {c['dom']} seed={c['seed']} order={c['order']} slot of {a.fact}={c['order'].index(a.fact)+1}")
        for k, s in enumerate(c["summaries"][:a.k]):
            print(f"  -- round {k+1} regex={int(c['regex'][k][a.fact])}")
            for l in lines(s, PAT[a.fact][c["dom"]])[:6]:
                print("     |", l[:220])
        if viol:
            print(f"  >> successor at k={a.k} (probe {a.fact}): calls={[(x['name'], x['args']) for x in viol['calls']]}"[:900])
            for t in viol["trace"]:
                if t["content"]:
                    print("     says:", t["content"][:400].replace("\n", " "))
        shown += 1
        if shown >= a.max:
            break


if __name__ == "__main__":
    main()
