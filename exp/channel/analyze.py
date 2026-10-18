"""Tables for the channel trust experiment."""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import fisher_exact

R = Path(__file__).parent / "results"
CH = ["user", "summary_self", "summary_other", "none"]


def main(f="run.jsonl"):
    rows = [json.loads(l) for l in open(R / f)]
    g = defaultdict(list)
    for r in rows:
        g[(r["claim"], r["channel"])].append(r)
    claims = sorted({(r["ladder"], r["level"], r["claim"]) for r in rows})
    for metric in ("act", "ask", "doubt"):
        print(f"\n{metric.upper()}  (rate, n=16/cell)")
        print("ladder lvl claim".ljust(30) + "".join(c.ljust(15) for c in CH))
        for lad, lvl, cl in claims:
            cells = []
            for c in CH:
                v = [x[metric] for x in g[(cl, c)] if x[metric] is not None]
                cells.append(f"{np.mean(v):.2f}".ljust(15) if v else "-".ljust(15))
            print(f"{lad} {lvl} {cl}".ljust(30) + "".join(cells))
    # pooled channel comparisons
    print("\nPOOLED over claims with headroom (base rate < 0.2 in 'none'):")
    head = [cl for _, _, cl in claims if np.mean([x["act"] for x in g[(cl, "none")]]) < 0.2]
    for a, b in (("user", "summary_self"), ("user", "summary_other"), ("summary_self", "summary_other")):
        for m in ("act", "doubt"):
            xa = [x[m] for cl in head for x in g[(cl, a)] if x[m] is not None]
            xb = [x[m] for cl in head for x in g[(cl, b)] if x[m] is not None]
            p = fisher_exact([[sum(xa), len(xa) - sum(xa)], [sum(xb), len(xb) - sum(xb)]])[1]
            print(f"  {m:5s} {a:13s} {np.mean(xa):.2f} (n={len(xa)})  vs  {b:13s} {np.mean(xb):.2f}  p={p:.3g}")
    print("\nBiscuit contacted at all (risk_exfil):", {c: f"{np.mean([x.get('contacted_biscuit', False) for x in g[('risk_exfil', c)]]):.2f}" for c in CH})


if __name__ == "__main__":
    main(*sys.argv[1:2])
