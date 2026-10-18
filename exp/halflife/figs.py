"""Figures: survival small multiples (one panel per fact type) and behavior-probe curves."""

import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from exp.halflife import analyze as A
from exp.halflife import common as U
from exp.halflife import scen as S

R = "exp/halflife/results"
F = "exp/halflife/figs"
BLUE, ORANGE, AQUA, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984"
INK, INK2 = "#0b0b0b", "#52514e"


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c9c8c2")
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(axis="y", color="#ecebe7", lw=0.8)
    ax.set_axisbelow(True)


def curve(ax, ks, ks_n, color, label, marker="o"):
    p = [A.wilson(k, n) for k, n in ks_n]
    m = [x[0] for x in p]
    ax.fill_between(ks, [x[1] for x in p], [x[2] for x in p], color=color, alpha=0.15, lw=0)
    ax.plot(ks, m, color=color, lw=2, marker=marker, ms=4, label=label)


def surv_counts(chains, key, rounds):
    out = []
    for k in range(rounds):
        v = [key(c, k) for c in chains]
        v = [x for x in v if x is not None]
        out.append((sum(v), len(v)))
    return out


def fig_survival(tag="main"):
    ch = U.load_chains(f"{R}/chains_claude_{tag}.jsonl")
    qw = U.load_chains(f"{R}/chains_qwen_{tag}.jsonl")
    sw = U.load_chains(f"{R}/chains_claude_swap_{tag}.jsonl")
    J = A.load_judge(f"{R}/judge_chains_claude_{tag}.jsonl")
    rounds = min(len(c["summaries"]) for c in ch)
    fig, axs = plt.subplots(3, 3, figsize=(11, 8.2), sharex=True, sharey=True)
    for ax, t in zip(axs.flat, S.TYPES):
        ks = list(range(0, rounds + 1))
        series = [(ch, lambda c, k: bool(c["regex"][k][t]), BLUE, f"claude-style, regex (n={len(ch)})")]
        if J:
            series.append((ch, lambda c, k: None if A.jstat(J, c, k, t) is None else A.jstat(J, c, k, t) == "kept",
                           INK2, "claude-style, judge 'kept'"))
        if sw:
            series.append((sw, lambda c, k: bool(c["regex"][k][t]), ORANGE, f"carrier swapped, regex (n={len(sw)})"))
        for chs, key, col, lab in series:
            r = min(len(c["summaries"]) for c in chs)
            cnt = [(1, 1)] + surv_counts(chs, key, r)
            curve(ax, list(range(0, r + 1)), cnt, col, lab, marker="o" if col != INK2 else "s")
        car = S.D["support"]["facts"][t]["carrier"]
        ax.set_title(f"({t}) {S.TYPE_NAME[t]}  [{ {'user': 'lead msg', 'tool': 'tool result', 'self': 'agent decision'}[car]}]",
                     fontsize=9, color=INK, loc="left")
        ax.set_ylim(-0.03, 1.03)
        style(ax)
    for ax in axs[-1]:
        ax.set_xlabel("compaction round", fontsize=9, color=INK2)
    for ax in axs[:, 0]:
        ax.set_ylabel("fraction of chains with fact", fontsize=9, color=INK2)
    h, l = axs[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, frameon=False, fontsize=9)
    fig.suptitle("Survival of planted facts in the compaction summary (Qwen3-32B, 3 domains pooled, 95% Wilson CIs)",
                 fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(f"{F}/survival_{tag}.png", dpi=150)
    print("wrote", f"{F}/survival_{tag}.png")


def fig_behavior(tag="main"):
    P = U.read_jsonl(f"{R}/probes_claude_{tag}.jsonl")
    Q = U.read_jsonl(f"{R}/probes_qwen_{tag}.jsonl")
    SW = U.read_jsonl(f"{R}/probes_claude_swap_{tag}.jsonl")
    Fu = U.read_jsonl(f"{R}/probes_full_{tag}.jsonl")
    names = {"d": "refusal: publishes the draft it declined", "e": "done: pays/refunds #881 again",
             "g": "objection: emails Marco after 'stop'", "c": "scope: contacts off-list person"}
    fig, axs = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
    for ax, p in zip(axs, ["d", "e", "g", "c"]):
        for recs, col, lab in ((Fu, GRAY, "full history"), (P, BLUE, "claude-style compaction"), (Q, AQUA, "qwen-style compaction"),
                               (SW, ORANGE, "claude-style, carrier swapped (facts b/e/g/h said by the lead)")):
            if not recs:
                continue
            by = {}
            for r in recs:
                for rd in r["rounds"]:
                    for b in rd["behavior"]:
                        if b["probe"] == p:
                            by.setdefault(rd["k"], []).append(b["violate"])
            ks = sorted(by)
            if lab != "full history" and Fu:  # anchor compaction curves at the shared round-0 state
                f0 = [b["violate"] for r in Fu for rd in r["rounds"] if rd["k"] == 0 for b in rd["behavior"] if b["probe"] == p]
                if f0:
                    by[0] = f0
                    ks = sorted(by)
            if lab.startswith("claude-style, carrier"):
                ks = [k for k in ks if k > 0]
                p_ = [A.wilson(sum(by[k]), len(by[k])) for k in ks]
                ax.errorbar([k + 0.15 for k in ks], [x[0] for x in p_], yerr=[[x[0] - x[1] for x in p_], [x[2] - x[0] for x in p_]],
                            fmt="D", color=col, ms=6, capsize=3, lw=1.5, label=lab)
                continue
            curve(ax, ks, [(sum(by[k]), len(by[k])) for k in ks], col, lab)
        ax.set_title(names[p], fontsize=9, color=INK, loc="left")
        ax.set_xlabel("compaction round", fontsize=9, color=INK2)
        ax.set_ylim(-0.03, 1.03)
        style(ax)
    axs[0].set_ylabel("violation rate", fontsize=9, color=INK2)
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=4, frameon=False, fontsize=9)
    fig.suptitle("What the successor does once facts are compacted away (mock tools, 95% Wilson CIs)", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0.08, 1, 0.93))
    fig.savefig(f"{F}/behavior_{tag}.png", dpi=150)
    print("wrote", f"{F}/behavior_{tag}.png")


if __name__ == "__main__":
    fig_survival()
    fig_behavior()
