"""Figures. Usage: python figs.py main|decomp|recur|probe TAG"""
import collections, json, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from lib import *

FIG = os.path.join(os.path.dirname(__file__), "figs")
COL = {"full": "#4C72B0", "truncate": "#8C8C8C", "qwen": "#C44E52", "qwen_shipped": "#E8A0A0",
       "qwen_notrailer": "#DD8452", "codex": "#55A868"}


def bars(ax, groups, series, rate, title, ylabel="gated action executed"):
    w = 0.8 / len(series)
    x = np.arange(len(groups))
    for i, s in enumerate(series):
        ps, lo, hi = [], [], []
        for g in groups:
            k, n = rate(g, s)
            p, l, h = wilson(k, n)
            ps.append(p); lo.append(p - l); hi.append(h - p)
        ax.bar(x + (i - (len(series) - 1) / 2) * w, ps, w, yerr=[lo, hi], capsize=2,
               label=s, color=COL.get(s, None))
        for xx, p, h in zip(x + (i - (len(series) - 1) / 2) * w, ps, hi):
            ax.text(xx, p + h + 0.02, f"{100*p:.0f}", ha="center", fontsize=6)
    ax.set_xticks(x); ax.set_xticklabels(groups)
    ax.set_ylim(0, 1); ax.set_ylabel(ylabel); ax.set_title(title)
    ax.grid(axis="y", alpha=.3)


def fig_main(tag):
    rows = load(f"{RES}/rerun_{tag}.jsonl")
    # compose as-shipped qwen: fixed runs on untruncated summaries + shipped runs on truncated ones
    trunc = {(r["scen"], r["sum_idx"]) for r in rows if r["cond"] == "qwen_shipped"}
    for r in [r for r in rows if r["cond"] == "qwen" and (r["scen"], r["sum_idx"]) not in trunc]:
        rows.append({**r, "cond": "qwen_shipped_all"})
    for r in [r for r in rows if r["cond"] == "qwen_shipped"]:
        rows.append({**r, "cond": "qwen_shipped_all"})
    COL["qwen_shipped_all"] = COL["qwen_shipped"]
    scens = sorted({r["scen"] for r in rows}, key=["migration", "deploy", "email", "refund", "gitpush", "cleanup"].index)
    conds = ["full", "truncate", "qwen_shipped_all", "qwen", "qwen_notrailer", "codex"]
    evs = sorted({r["event"] for r in rows})
    fig, axes = plt.subplots(1, len(evs), figsize=(6.5 * len(evs), 4), squeeze=False)
    for ax, ev in zip(axes[0], evs):
        def rate(g, s):
            rs = [r for r in rows if r["event"] == ev and r["cond"] == s and (g == "pooled" or r["scen"] == g)]
            return sum(r["gated"] for r in rs), len(rs)
        bars(ax, scens + ["pooled"], conds, rate, f'next event: "{EVENTS[ev]}"')
    axes[0][0].legend(fontsize=7, ncol=2)
    fig.tight_layout(); fig.savefig(f"{FIG}/main_{tag}.png", dpi=150)


def fig_decomp(tag):
    rows = load(f"{RES}/decomp_{tag}.jsonl")
    cells = [c for c in ["orig", "R1:gated", "R0:gated", "R1:none", "R0:none", "R1:actcond", "R1:wait", "R1:cond"]
             if any(r["cell"] == c for r in rows)]
    frs = [f for f in ["user", "user_notrailer", "user_prov", "assistant", "system"] if any(r["framing"] == f for r in rows)]
    fig, ax = plt.subplots(figsize=(12, 4.5))
    fc = {"user": "#C44E52", "user_notrailer": "#DD8452", "user_prov": "#8172B3", "assistant": "#4C72B0", "system": "#55A868"}
    w = 0.8 / len(frs)
    x = np.arange(len(cells))
    for i, f in enumerate(frs):
        ps, lo, hi, xs = [], [], [], []
        for j, c in enumerate(cells):
            rs = [r for r in rows if r["cell"] == c and r["framing"] == f]
            if not rs:
                continue
            p, l, h = wilson(sum(r["gated"] for r in rs), len(rs))
            ps.append(p); lo.append(p - l); hi.append(h - p); xs.append(j)
            ax.text(j + (i - (len(frs) - 1) / 2) * w, p + 0.03 + (h - p), f"{100*p:.0f}%", ha="center", fontsize=7)
        ax.bar(np.array(xs) + (i - (len(frs) - 1) / 2) * w, ps, w, yerr=[lo, hi], capsize=2, label=f, color=fc[f])
    labels = {"orig": "original\nsummary", "R1:gated": "restriction +\nnext: \"do X\"", "R0:gated": "restriction -\nnext: \"do X\"",
              "R1:none": "restriction +\nX not in plan", "R0:none": "restriction -\nX not in plan",
              "R1:actcond": "R+ next:\n\"do X - only\nafter approval\"", "R1:wait": "R+ next:\n\"wait for approval\nbefore X\"",
              "R1:cond": "R+ pending: X after\napproval; next:\nunrelated step", "R1:safe": "R+ next:\nwait"}
    ax.set_xticks(x); ax.set_xticklabels([labels[c] for c in cells], fontsize=8)
    ax.set_ylim(0, 1.1); ax.set_ylabel("gated action executed"); ax.grid(axis="y", alpha=.3)
    if "R1:gated" in cells:
        ax.axvline(4.5, color="k", lw=.5, ls=":")
    ax.set_title(f"Crossed summary edits on real qwen summaries (pooled over 4 scenarios; n=96/bar; {tag})")
    ax.legend(fontsize=8, title="summary placement")
    fig.tight_layout(); fig.savefig(f"{FIG}/decomp_{tag}.png", dpi=150)


def fig_recur(tag):
    from labels import label
    rows = load(f"{RES}/recur_{tag}.jsonl")
    for r in rows:
        if "summary" in r:
            r["labels"] = label(r["summary"], r["scen"])
    styles = ["full", "qwen", "codex"]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    for st in styles:
        rr = [r for r in rows if r["style"] == st]
        ks = sorted({r["round"] for r in rr})
        def series(f):
            ps, lo, hi = [], [], []
            for k in ks:
                kk, nn = f([r for r in rr if r["round"] == k])
                p, l, h = wilson(kk, nn); ps.append(p); lo.append(p - l); hi.append(h - p)
            return ps, lo, hi
        p, l, h = series(lambda rs: (sum(x["gated"] for r in rs for x in r["runs"]), sum(len(r["runs"]) for r in rs)))
        axes[0].errorbar(ks, p, yerr=[l, h], marker="o", label=st, color=COL[st], capsize=2)
        if st != "full":
            p, l, h = series(lambda rs: (sum(r["labels"]["restr"] for r in rs), len(rs)))
            axes[1].errorbar(ks, p, yerr=[l, h], marker="o", label=st, color=COL[st], capsize=2)
            p, l, h = series(lambda rs: (sum(r["labels"]["plan_act"] for r in rs), len(rs)))
            axes[2].errorbar(ks, p, yerr=[l, h], marker="o", label=st, color=COL[st], capsize=2)
    for ax, t in zip(axes, ["successor executes gated action", "restriction present in summary text\n(codex also keeps user msgs verbatim)",
                            "gated action listed in plan (pending/next)"]):
        ax.set_title(t, fontsize=10); ax.set_xlabel("compaction round (full: same filler, no compaction)")
        ax.set_ylim(-0.02, 1.02); ax.grid(alpha=.3)
    axes[0].legend(fontsize=8)
    fig.suptitle("Recursive compaction (migration + deploy; 4 chains/style/scenario; 4 successors per summary)", fontsize=10)
    fig.tight_layout(); fig.savefig(f"{FIG}/recur_{tag}.png", dpi=150)


if __name__ == "__main__":
    {"main": fig_main, "decomp": fig_decomp, "recur": fig_recur}[sys.argv[1]](sys.argv[2])
