"""Addendum figures: (left) refusal-line factorial; (right) violation at k=6 by harness for probes d/e/g."""

from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from exp.halflife import analyze as A
from exp.halflife import common as U
from exp.halflife.figs import AQUA, BLUE, GRAY, INK, INK2, ORANGE, style

R = "exp/halflife/results"
VIOLET = "#4a3aa7"


def main():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.8), gridspec_kw={"width_ratios": [1.25, 1]})
    E = [e for e in U.read_jsonl(f"{R}/edits2_main.jsonl") if e["trigger"] == "tracker"]
    by = defaultdict(list)
    for e in E:
        by[e["cond"]] += e["violate"]
    order = ["asis", "strip", "reason_first_constraint", "reason_first_problem", "reason_passive_constraint",
             "reason_passive_problem", "noreason_first_constraint", "noreason_first_problem",
             "noreason_passive_constraint", "noreason_passive_problem"]
    labels = ["as\nwritten", "refusal\nremoved", "reason\n1st\nconstr.", "reason\n1st\nproblem",
              "reason\npassive\nconstr.", "reason\npassive\nproblem", "no reason\n1st\nconstr.", "no reason\n1st\nproblem",
              "no reason\npassive\nconstr.", "no reason\npassive\nproblem"]
    for i, c in enumerate(order):
        v = by.get(c, [])
        if not v:
            continue
        p, lo, hi = A.wilson(sum(v), len(v))
        col = GRAY if i < 2 else (BLUE if "first" in c else ORANGE)
        ax1.bar(i, p, color=col, width=0.7)
        ax1.errorbar(i, p, yerr=[[p - lo], [hi - p]], color=INK2, capsize=3, lw=1)
    ax1.set_xticks(range(len(order)))
    ax1.set_xticklabels(labels, fontsize=7, color=INK2)
    ax1.set_ylim(0, 1.05)
    ax1.set_ylabel("publishes the declined draft", fontsize=9, color=INK2)
    ax1.set_title("Same k=6 states (n=24), only the refusal line edited  (blue: first person, orange: passive)",
                  fontsize=9, color=INK, loc="left")
    style(ax1)

    conds = [("full", "probes_full_main.jsonl", GRAY), ("claude", "probes_claude_main.jsonl", BLUE),
             ("codex", "probes_codex_main.jsonl", AQUA), ("claude + ledger", "probes_ledger_main.jsonl", VIOLET),
             ("claude + first person", "probes_fp_main.jsonl", "#eda100"), ("first person + ledger", "probes_fpledger_main.jsonl", "#e87ba4"),
             ("claude + commitment pinning", "probes_pin_main.jsonl", "#e34948")]
    probes = [("d", "refusal"), ("e", "double pay"), ("g", "emails Marco")]
    w = 0.115
    for j, (lab, f, col) in enumerate(conds):
        agg = defaultdict(list)
        for r in U.read_jsonl(f"{R}/{f}"):
            for rd in r["rounds"]:
                if rd["k"] != 6:
                    continue
                for b in rd["behavior"]:
                    agg[b["probe"]].append(U.rescore(r["dom"], b["probe"], b["calls"])["violate"])
        for i, (p, _) in enumerate(probes):
            v = agg.get(p, [])
            if not v:
                continue
            pr, lo, hi = A.wilson(sum(v), len(v))
            x = i + (j - 3) * w
            ax2.bar(x, pr, width=w * 0.92, color=col, label=f"{lab} (n={len(v)})" if i == 0 else None)
            ax2.errorbar(x, pr, yerr=[[pr - lo], [hi - pr]], color=INK2, capsize=2, lw=1)
    ax2.set_xticks(range(len(probes)))
    ax2.set_xticklabels([n for _, n in probes], fontsize=9, color=INK2)
    ax2.set_ylim(0, 1.05)
    ax2.set_ylabel("violation rate at round 6", fontsize=9, color=INK2)
    ax2.set_title("Harness comparison at round 6", fontsize=9, color=INK, loc="left")
    ax2.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)
    style(ax2)
    fig.tight_layout()
    fig.savefig("exp/halflife/figs/addendum_main.png", dpi=150)
    print("wrote exp/halflife/figs/addendum_main.png")


if __name__ == "__main__":
    main()
