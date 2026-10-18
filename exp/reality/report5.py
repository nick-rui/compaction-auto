"""Generality table (exp/reality/results/general.jsonl). python -m exp.reality.report5"""
import collections
from scipy.stats import fisher_exact
from exp.reality import common as K
from exp.reality.report import load

rows = load("general.jsonl")
g = collections.defaultdict(list)
for r in rows:
    g[(r["src"], r["scen"], r["var"])].append(bool(r["harm"]))
    g[(r["src"], "ALL", r["var"])].append(bool(r["harm"]))
for src, scen in sorted({(a, b) for a, b, _ in g}):
    base = g[(src, scen, "line")]
    out = [f"{src:9s} {scen:10s}"]
    for var in ("line", "noline", "safe"):
        xs = g[(src, scen, var)]
        p = fisher_exact([[sum(base), len(base) - sum(base)], [sum(xs), len(xs) - sum(xs)]])[1] if var != "line" and xs else float("nan")
        out.append(f"{var}: {K.fmt(sum(xs), len(xs))}" + (f" (p={p:.2g})" if var != "line" else ""))
    print(" | ".join(out))
