"""python exp/trust/gap_analyze.py --act gap_judged,gapattr_judged --probe gapprobe"""

import argparse
import collections
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from exp.trust.analyze import fmt, wilson  # noqa: E402
from exp.trust.gap import SCEN  # noqa: E402

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
FIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs")
LV = [f"L{i}" for i in range(1, 11)]
KIND = {c[0]: c[1] for c in SCEN["report"]["claims"]}


def load(tags):
    rows = []
    for t in tags:
        p = os.path.join(RES, f"{t}.jsonl")
        if os.path.exists(p):
            rows += [json.loads(l) for l in open(p)]
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--act", default="gap_judged,gapattr_judged")
    ap.add_argument("--probe", default="gapprobe")
    ap.add_argument("--name", default="gap")
    a = ap.parse_args()
    rows = load(a.act.split(","))
    probe = load(a.probe.split(",")) if a.probe else []
    C = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        for key in [(r["scn"], r["channel"], r["branch"], r["lv"]), ("ALL", r["channel"], r["branch"], r["lv"]),
                    ("ALL", r["channel"], r["branch"], "ALL"), (r["scn"], r["channel"], r["branch"], "ALL")]:
            c = C[key]
            c["n"] += 1
            c["act"] += r["act"]
            c["ask"] += r["ask"]
            if r.get("doubt") is not None:
                c["dn"] += 1
                c["doubt"] += r["doubt"]
                c["skep"] += bool(r["doubt"] or r["ask"])
            if r["lv"] == "none":
                for lv, v in r["act_by_lv"].items():
                    C[(r["scn"], "none", r["branch"], lv)]["act"] += v
                    C[(r["scn"], "none", r["branch"], lv)]["n"] += 1
                    C[("ALL", "none", r["branch"], lv)]["act"] += v
                    C[("ALL", "none", r["branch"], lv)]["n"] += 1
    P = collections.defaultdict(lambda: collections.Counter())
    for r in probe:
        if r["flags_claim"] is None:
            continue
        for key in [(r["scn"], r["channel"], r["lv"]), ("ALL", r["channel"], r["lv"]), ("ALL", r["channel"], "ALL"),
                    (r["scn"], r["channel"], "ALL")]:
            P[key]["n"] += 1
            P[key]["f"] += r["flags_claim"]

    chans = [c for c in ["user", "sum_bare", "sum_user", "sum_self", "sum_tool", "tool"] if any(k[1] == c for k in C)]
    for br in ("act", "ask"):
        print(f"\n### branch={br}-first, pooled over 3 scenarios: ACT | DOUBT-or-ASK (unprompted skepticism)")
        cs = [c for c in chans if C[("ALL", c, br, "ALL")]["n"]]
        print("| level | " + " | ".join(cs) + " | no-claim act |")
        print("|---" * (len(cs) + 2) + "|")
        for lv in LV + ["ALL"]:
            cells = []
            for ch in cs:
                c = C[("ALL", ch, br, lv)]
                cells.append(f"act {fmt(c['act'], c['n'])}<br>skep {fmt(c['skep'], c['dn'])}")
            b = C[("ALL", "none", br, lv)]
            print(f"| {lv} {KIND.get(lv, '')} | " + " | ".join(cells) + f" | {fmt(b['act'], b['n']) if lv != 'ALL' else ''} |")
    print("\n### per scenario (act-first): act / skep, pooled over levels")
    for scn in SCEN:
        print(scn, "  ".join(f"{ch}: act {fmt(C[(scn, ch, 'act', 'ALL')]['act'], C[(scn, ch, 'act', 'ALL')]['n'])} "
                             f"skep {fmt(C[(scn, ch, 'act', 'ALL')]['skep'], C[(scn, ch, 'act', 'ALL')]['dn'])}" for ch in chans))
    print("\n### per scenario x level, act-first, sum_bare: act/skep")
    for scn in SCEN:
        print(scn, " ".join(f"{lv}:{C[(scn, 'sum_bare', 'act', lv)]['act']}/{C[(scn, 'sum_bare', 'act', lv)]['n']}"
                            f"({C[(scn, 'sum_bare', 'act', lv)]['skep']})" for lv in LV))
        print(scn + "(ask)", " ".join(f"{lv}:{C[(scn, 'sum_bare', 'ask', lv)]['act']}/{C[(scn, 'sum_bare', 'ask', lv)]['n']}"
                                     f"({C[(scn, 'sum_bare', 'ask', lv)]['skep']})" for lv in LV))
    if probe:
        pch = [c for c in chans if P[("ALL", c, "ALL")]["n"]]
        print("\n### PROBED: flags the claim when asked 'anything implausible?' (judge), pooled over scenarios")
        print("| level | " + " | ".join(pch) + " |")
        print("|---" * (len(pch) + 1) + "|")
        for lv in LV + ["ALL"]:
            print(f"| {lv} {KIND.get(lv, '')} | " + " | ".join(fmt(P[('ALL', c, lv)]['f'], P[('ALL', c, lv)]['n']) for c in pch) + " |")

    # figure
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.2), sharey=True)
    col = {"user": "#ff7f0e", "sum_bare": "#1f77b4", "sum_user": "#aec7e8", "sum_self": "#9467bd", "sum_tool": "#8c564b",
           "tool": "#d62728"}
    xs = range(1, 11)
    for ai, (title, fn) in enumerate([
        ("P(act on claim), act-first", lambda ch: [(C[("ALL", ch, "act", lv)]["act"], C[("ALL", ch, "act", lv)]["n"]) for lv in LV]),
        ("P(unprompted doubt, judge), act-first", lambda ch: [(C[("ALL", ch, "act", lv)]["doubt"], C[("ALL", ch, "act", lv)]["dn"]) for lv in LV]),
        ("P(flags claim when asked)", lambda ch: [(P[("ALL", ch, lv)]["f"], P[("ALL", ch, lv)]["n"]) for lv in LV]),
    ]):
        ax = axes[ai]
        for j, ch in enumerate(chans):
            v = fn(ch)
            pts = [(x + (j - 2.5) * 0.06, *wilson(k, n)) for x, (k, n) in zip(xs, v) if n]
            if not pts:
                continue
            ax.errorbar([p[0] for p in pts], [p[1] for p in pts],
                        yerr=[[max(0, p[1] - p[2]) for p in pts], [max(0, p[3] - p[1]) for p in pts]],
                        marker="o", ms=4, capsize=2, lw=1.2, color=col[ch], label=ch)
        ax.set_xticks(list(xs))
        ax.set_xticklabels([f"L{i}\n{KIND[f'L{i}']}" for i in xs], fontsize=6)
        ax.set_title(title, fontsize=10)
        ax.set_ylim(-0.03, 1.03)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=6)
    plt.suptitle("Qwen3-32B, 3 scenarios (report / email / ops) pooled; 95% Wilson CIs", fontsize=10)
    plt.tight_layout()
    os.makedirs(FIG, exist_ok=True)
    p = os.path.join(FIG, f"{a.name}_ladder.png")
    plt.savefig(p, dpi=130)
    print("saved", p)


if __name__ == "__main__":
    main()
