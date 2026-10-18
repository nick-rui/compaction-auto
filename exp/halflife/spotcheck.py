"""Print random judge items next to the summary evidence for manual spot-checking; and judge vs think-judge agreement.

usage: python -m exp.halflife.spotcheck --n 16 [--think_file judge_think_chains_claude_main.jsonl]
"""

import argparse
import random
import re
from collections import Counter

from exp.halflife import common as U
from exp.halflife.cases import PAT

R = "exp/halflife/results"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--judge", default="judge_chains_claude_main.jsonl")
    ap.add_argument("--think_file", default=None)
    a = ap.parse_args()
    ch = {(c["dom"], c["seed"]): c for c in U.load_chains(f"{R}/chains_claude_main.jsonl")}
    J = [r for r in U.read_jsonl(f"{R}/{a.judge}") if r.get("judge")]
    rng = random.Random(a.seed)
    items = [(r, t) for r in J for t in "abcdefghi" if isinstance(r["judge"].get(t), dict)]
    # oversample non-trivial labels
    pick = [x for x in items if x[0]["judge"][x[1]]["status"] in ("distorted", "weakened")]
    rng.shuffle(pick)
    rest = [x for x in items if x not in pick]
    rng.shuffle(rest)
    sel = pick[: a.n // 2] + rest[: a.n - min(len(pick), a.n // 2)]
    for r, t in sel:
        c = ch[(r["dom"], r["seed"])]
        s = c["summaries"][r["k"] - 1]
        ev = [l.strip()[:200] for l in s.splitlines() if re.search(PAT[t][r["dom"]], l, re.I)][:5]
        j = r["judge"][t]
        print(f"--- {r['dom']} seed={r['seed']} k={r['k']} fact={t} judge={j['status']}/{j.get('distortion')} regex={int(c['regex'][r['k']-1][t])}")
        print("    judge quote:", j.get("quote"))
        for l in ev:
            print("    |", l)
    if a.think_file:
        T = {(r["dom"], r["seed"], r["k"]): r["judge"] for r in U.read_jsonl(f"{R}/{a.think_file}") if r.get("judge")}
        agree = Counter()
        for r in J:
            tj = T.get((r["dom"], r["seed"], r["k"]))
            if not tj:
                continue
            for t in "abcdefghi":
                x, y = r["judge"].get(t, {}), tj.get(t, {})
                if isinstance(x, dict) and isinstance(y, dict):
                    agree["n"] += 1
                    agree["exact"] += x.get("status") == y.get("status")
                    agree["kept_bin"] += (x.get("status") == "kept") == (y.get("status") == "kept")
        print(f"\nnon-thinking vs thinking judge: exact status {agree['exact']}/{agree['n']}, kept-vs-not {agree['kept_bin']}/{agree['n']}")


if __name__ == "__main__":
    main()
