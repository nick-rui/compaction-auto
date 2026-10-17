"""Figures for the mistake-laundering experiment.  python -m exp.honesty.figs"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .analyze import summaries_df, wilson
from .report import enrich

FIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs")
COLORS = {"full": "#4C72B0", "qwen": "#DD8452", "codex": "#55A868", "truncate": "#8C8C8C"}


def bars(ax, labels, ks, ns, colors, ref=None):
    p = np.array(ks) / np.maximum(1, np.array(ns))
    ci = np.array([wilson(k, n) for k, n in zip(ks, ns)])
    ax.bar(range(len(labels)), p, yerr=np.clip(np.vstack([p - ci[:, 0], ci[:, 1] - p]), 0, None), capsize=4, color=colors)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8)
    for i, (pp, n) in enumerate(zip(p, ns)):
        ax.text(i, min(1.0, ci[i, 1]) + 0.02, f"{pp:.0%}\nn={n}", ha="center", va="bottom", fontsize=7)
    ax.set_ylim(0, 1.18)
    if ref is not None:
        ax.axhline(ref, ls="--", lw=1, color=COLORS["full"])


def main():
    os.makedirs(FIG, exist_ok=True)
    d = enrich("pilot")
    d = d[d.tag == ""]
    conds = ["full", "qwen", "codex", "truncate"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2), gridspec_kw={"width_ratios": [1, 2.6]})
    g = d.groupby("cond").disc
    bars(axes[0], conds, [g.sum()[c] for c in conds], [g.count()[c] for c in conds], [COLORS[c] for c in conds])
    axes[0].set_ylabel("P(successor tells the user about the shortcut)")
    axes[0].set_title("11 scenarios pooled (6 samples each)")
    pt = d.pivot_table(index="scen", columns="cond", values="disc", aggfunc="mean").sort_values("full", ascending=False)
    x = np.arange(len(pt))
    w = 0.2
    for i, c in enumerate(conds):
        axes[1].bar(x + (i - 1.5) * w, pt[c].values, w, color=COLORS[c], label=c)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(pt.index, rotation=30, ha="right", fontsize=8)
    axes[1].set_ylim(0, 1.05)
    axes[1].legend(fontsize=8, ncol=4)
    axes[1].set_title("Per scenario")
    fig.suptitle("'Anything I should know before I ship?' after the agent's own mid-history shortcut (Qwen3-32B)")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "disclosure_main.png"), dpi=150)

    # mechanism + interventions
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.4), gridspec_kw={"width_ratios": [1, 2.2]})
    s = summaries_df("pilot")
    s["cond"] = s["style"]
    m = d.merge(s[["scen", "cond", "k", "flag"]], on=["scen", "cond", "k"])
    labs, ks, ns, cols = [], [], [], []
    for st in ["qwen", "codex"]:
        ss = s[s.style == st]
        labs.append(f"{st}\nsummary\nflags it"); ks.append(int(ss.flag.sum())); ns.append(len(ss)); cols.append("#bbbbbb")
        for f in [False, True]:
            gg = m[(m.cond == st) & (m.flag == f)]
            labs.append(f"{st}\nP(disc|\nflag={'Y' if f else 'N'})"); ks.append(int(gg.disc.sum())); ns.append(len(gg)); cols.append(COLORS[st])
    bars(axes[0], labs, ks, ns, cols)
    axes[0].set_title("Fact is kept (~97-100% keyword hit) but is it\nflagged as open? And does that predict disclosure?", fontsize=9)
    items = [("qwen\n(orig)", d[(d.cond == "qwen") & (d.k < 4)])]
    di = pd.concat([x for x in [enrich("interv", src="pilot"), enrich("intervc", src="pilot")] if len(x)])
    for c, lab in [("qwen_euph", "qwen\n+euph line"), ("qwen_neu", "qwen\n+neutral line"), ("qwen_acc", "qwen\n+accurate line"),
                   ("qwen_swap", "qwen summary\nin codex frame"), ("codex_swap", "codex summary\nin qwen frame")]:
        items.append((lab, di[di.cond == c]))
    h = enrich("honest")
    if len(h):
        items.append(("qwen_honest\n(prompt fix)", h[h.cond == "qwen_honest"]))
    items.append(("codex\n(orig)", d[d.cond == "codex"]))
    cmap = ["#DD8452"] * 4 + ["#c5b0d5", "#c5b0d5"] + (["#2ca02c"] if len(h) else []) + ["#55A868"]
    bars(axes[1], [i[0] for i in items], [int(i[1].disc.sum()) for i in items], [len(i[1]) for i in items], cmap,
         ref=d[d.cond == "full"].disc.mean())
    axes[1].set_title("Causal edits (dashed = full-context rate)", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "mechanism.png"), dpi=150)
    print("saved figs")


if __name__ == "__main__":
    main()


def addendum():
    """Trailer ablation (constructed) + on-policy replication."""
    d = enrich("pilot")
    d = d[d.tag == ""]
    tr = enrich("trail", src="pilot")
    op = enrich("onpol")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2), gridspec_kw={"width_ratios": [1.5, 1]})
    items = [("full", d[d.cond == "full"], COLORS["full"]), ("qwen\n(as shipped)", d[d.cond == "qwen"], COLORS["qwen"]),
             ("qwen\n-'Got it' ack", tr[tr.cond == "qwen_noack"], "#f0b27a"), ("qwen\n-'Resume...' trailer", tr[tr.cond == "qwen_notrail"], "#f0b27a"),
             ("qwen\n-both", tr[tr.cond == "qwen_bare"], "#f0b27a"), ("codex", d[d.cond == "codex"], COLORS["codex"])]
    bars(axes[0], [i[0] for i in items], [int(i[1].disc.sum()) for i in items], [len(i[1]) for i in items], [i[2] for i in items])
    axes[0].set_ylabel("P(successor discloses the shortcut)")
    axes[0].set_title("Same qwen summaries, rebuild ablated (constructed, n=66 each)", fontsize=9)
    conds = ["full", "qwen", "codex", "truncate"]
    bars(axes[1], conds, [int(op[op.cond == c].disc.sum()) for c in conds], [int((op.cond == c).sum()) for c in conds], [COLORS[c] for c in conds])
    axes[1].set_title(f"On-policy: Qwen's own corner-cutting rollouts ({op.scen.nunique()} traj x 4 seeds)", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "addendum.png"), dpi=150)
    print("saved addendum")


if __name__ == "__main__":
    addendum()
