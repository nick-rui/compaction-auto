"""Tables with Wilson 95% CIs for provenance results.

python -m exp.provenance.stats pub50 pubuser dep50 depuser
"""

import json
import os
import re
import sys

import numpy as np
import pandas as pd

from exp.provenance.analyze import ACT, classify_lines, reexposed, sections_with_marker
from exp.provenance.run import RES

pd.set_option("display.width", 220)
pd.set_option("display.max_rows", 500)
pd.set_option("display.max_columns", 30)


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100*k/n:.0f}% [{100*lo:.0f},{100*hi:.0f}]"


def load(*tags):
    out = []
    for t in tags:
        out += [json.loads(l) for l in open(os.path.join(RES, f"{t}.jsonl"))]
    return out


def annotate(r):
    scen = r["scen"]
    act = re.compile(ACT[scen], re.I)
    texts = "\n".join(s.get("content") or "" for s in r["steps"])
    r["announced"] = bool(act.search(texts)) and not r["followed"]
    r["reexp"] = reexposed(r)
    if r.get("summary"):
        cls, lines = classify_lines(scen, r["summary"])
        r["mention"] = cls != "absent"
        r["attr_regex"] = cls
        if r["cond"] in ("qwen", "qwenfix"):
            secs = sections_with_marker(r["summary"], act)
            r["sections"] = secs
            r["in_user_msgs"] = "all_user_messages" in secs
            r["in_pending_or_next"] = bool({"pending_tasks", "next_step"} & set(secs))
            r["in_primary"] = "primary_request_and_intent" in secs
    return r


def main(tags):
    recs = [annotate(r) for r in load(*tags)]
    df = pd.DataFrame(recs)
    keys = ["scen", "inject", "guard", "flag", "think", "cond"]
    rows = []
    for k, g in df.groupby(keys):
        n = len(g)
        row = dict(zip(keys, k))
        row["n"] = n
        row["followed"] = fmt(int(g.followed.sum()), n)
        row["fol_no_reexp"] = fmt(int((g.followed & ~g.reexp).sum()), n)
        row["announced_not_done"] = f"{100*g.announced.mean():.0f}%"
        if "mention" in g and g["mention"].notna().any():
            m = g["mention"].fillna(False).astype(bool)
            row["mention"] = f"{100*m.mean():.0f}%"
            row["fol|mention"] = fmt(int((g.followed & m).sum()), int(m.sum())) if m.sum() else "-"
            row["fol|absent"] = fmt(int((g.followed & ~m).sum()), int((~m).sum())) if (~m).sum() else "-"
            row["attr_user%"] = f"{100*(g.attr_regex.isin(['user','mixed'])).mean():.0f}%"
        if "in_user_msgs" in g and g["in_user_msgs"].notna().any():
            row["in_all_user_msgs"] = f"{100*g.in_user_msgs.fillna(False).astype(bool).mean():.0f}%"
            row["in_pending/next"] = f"{100*g.in_pending_or_next.fillna(False).astype(bool).mean():.0f}%"
            row["in_primary"] = f"{100*g.in_primary.fillna(False).astype(bool).mean():.0f}%"
        if "truncated" in g and g["truncated"].notna().any():
            row["trunc"] = f"{100*g.truncated.fillna(False).astype(bool).mean():.0f}%"
        rows.append(row)
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    return df


if __name__ == "__main__":
    main(sys.argv[1:])
