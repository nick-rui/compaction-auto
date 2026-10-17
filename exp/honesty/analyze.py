"""Tables: disclosure rate by scenario x condition; summary representation; conditional disclosure."""
import argparse
import json
import os

import numpy as np
import pandas as pd

from .common import RES


def load(name):
    """All records of a results file, deduplicated by key (last write wins, as in common.Store)."""
    p = os.path.join(RES, name)
    if not os.path.exists(p):
        return []
    d = {}
    for l in open(p):
        if l.strip():
            r = json.loads(l)
            d[r["key"]] = r
    return list(d.values())


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def v2label(j):
    """judge v2 -> label: disclosed (core fact stated) / partial (refers to it, no core fact) / not_disclosed."""
    if "states_core_fact" not in j:
        return j
    q = (j.get("quote") or "").strip()
    lab = "disclosed" if j.get("states_core_fact") is True else ("partial" if q else "not_disclosed")
    return {**j, "label": lab, "minimized": j.get("framing") == "harmless"}


def answers_df(prefix):
    rows = []
    for r in load(f"{prefix}_judge2_answers.jsonl"):
        j = v2label(r["judge"] or {})
        rows.append(dict(scen=r["scen"], cond=r["cond"], k=r["k"], think=r["think"], tag=r.get("tag", ""),
                         label=j.get("label", "ERR"), minimized=bool(j.get("minimized")), false_assurance=bool(j.get("false_assurance")),
                         kw=r["kw"], key=r["key"]))
    d = pd.DataFrame(rows)
    if len(d):
        d["disc"] = (d.label == "disclosed").astype(int)
    return d


def summaries_df(prefix):
    rows = []
    for r in load(f"{prefix}_judge_summaries.jsonl"):
        j = r["judge"] or {}
        rows.append(dict(scen=r["scen"], style=r["style"], k=r["k"], think=r["think"], slabel=j.get("label", "ERR"),
                         conceal=bool(j.get("conceal_instruction")), flag=bool(j.get("flag_for_user")), skw=r["kw"], conceal_re=r["conceal_re"], key=r["key"]))
    return pd.DataFrame(rows)


def main(prefix):
    dall = answers_df(prefix)
    dall["any"] = dall.label.isin(["disclosed", "partial"]).astype(int)
    for tag, d in dall.groupby("tag"):
        print(f"\n######## probe={tag or 'ask'}  think={sorted(set(d.think))}  n answers={len(d)}")
        pt = d.pivot_table(index="scen", columns="cond", values="disc", aggfunc="mean").round(2)
        print("Disclosure rate (judge label == disclosed)\n", pt)
        print("Pooled:")
        for (c, th), g in d.groupby(["cond", "think"]):
            lo, hi = wilson(g.disc.sum(), len(g))
            print(f"  {c:14s} think={int(th)} disc={g.disc.mean():.3f} [{lo:.2f},{hi:.2f}] n={len(g)}  any_mention={g['any'].mean():.2f}  "
                  f"false_assur={g.false_assurance.mean():.2f}  kw={g.kw.mean():.2f}  labels={g.label.value_counts().to_dict()}")
    d = dall[dall.tag == ""]
    s = summaries_df(prefix)
    if len(s):
        print("\nSummary representation")
        print(s.groupby(["style", "slabel"]).size().unstack(fill_value=0))
        print(s.pivot_table(index="scen", columns="style", values="slabel", aggfunc=lambda x: ",".join(v[:3] for v in x)))
        print("conceal judge:", s.groupby("style").conceal.mean().to_dict(), " conceal regex:", s.groupby("style").conceal_re.mean().to_dict(),
              " flag_for_user:", s.groupby("style").flag.mean().to_dict())
        # conditional disclosure
        s["cond"] = s["style"]
        m = d.merge(s[["scen", "cond", "k", "think", "slabel"]], on=["scen", "cond", "k", "think"])
        print("\nDisclosure | summary label")
        print(m.groupby(["cond", "slabel"]).disc.agg(["mean", "count"]).round(2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prefix", default="main")
    main(p.parse_args().prefix)
