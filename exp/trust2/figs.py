"""PYTHONPATH=. .venv/bin/python exp/trust2/figs.py  -> exp/trust2/figs/headline.png"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from exp.trust2 import analyze as An  # noqa: E402
from exp.trust2 import scen as S  # noqa: E402

FIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs")
os.makedirs(FIG, exist_ok=True)
COL = {"full": "#555555", "claude": "#d95f02", "claude_ns": "#fdb863", "qwen": "#1b9e77", "codex": "#7570b3", "full_sfx": "#999999"}


def bars(ax, groups, conds, getter, title, ylabel):
    w = 0.8 / len(conds)
    for i, c in enumerate(conds):
        ps, lo, hi = [], [], []
        for g in groups:
            k, n = getter(g, c)
            p, l, h = An.wilson(k, n)
            ps.append(p * 100 if n else np.nan)
            lo.append((p - l) * 100 if n else 0)
            hi.append((h - p) * 100 if n else 0)
        x = np.arange(len(groups)) + (i - (len(conds) - 1) / 2) * w
        ax.bar(x, ps, w, yerr=[lo, hi], color=COL[c], label=c, capsize=2)
    ax.set_xticks(np.arange(len(groups)))
    ax.set_xticklabels(groups, fontsize=8)
    ax.set_ylim(0, 105)
    ax.set_title(title, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=8)


def main():
    A = An.rescore([r for r in An.load("act.jsonl") if not r.get("error")])
    P = An.load("probe.jsonl")
    CA = An.load("chain_act.jsonl")
    CS = An.load("chain_sums.jsonl")
    rows = [r for r in A if r["lv"] != "none" and r["pos"] in S.POS]
    fig, axs = plt.subplots(1, 4, figsize=(17, 3.8))

    def g_act(key, hd, lvs=None):
        def f(g, c):
            rs = [r for r in rows if r["hdoubt"] == hd and r["cond"] == c and r["pos"] == g and (lvs is None or r["lv"] in lvs)]
            return An.rate(rs, key)
        return f

    bars(axs[0], ["U", "T", "A"], ["full", "claude", "qwen", "codex"], g_act("act", 0),
         "No prior doubt: ACT on the planted claim\n(U=user turn, T=tool output, A=agent note)", "% of successor rollouts")
    bars(axs[1], ["U", "T", "A"], ["full", "claude"],
         lambda g, c: An.rate([p for p in P if p["pos"] == g and p["cond"] == c and p["doubt"] == 0], "flags_claim"),
         "No prior doubt: claim flagged when ASKED\n('anything implausible?')", "% flagged")
    bars(axs[2], ["U", "T", "A"], ["full", "claude", "claude_ns", "qwen"], g_act("act", 1, ("L4", "L8")),
         "Agent doubted the claim earlier (L4, L8):\nACT anyway", "% of successor rollouts")
    rounds = [1, 2, 3, 4]
    for c, lab in (("claude", "after k compactions"), ("full_rumor", "full history, same depth")):
        ys, lo, hi = [], [], []
        for r in rounds:
            k, n = An.rate([x for x in CA if x["round"] == r and x["cond"] == c and x["scn"] == "report"], "act")
            p, l, h = An.wilson(k, n)
            ys.append(100 * p)
            lo.append(100 * (p - l))
            hi.append(100 * (h - p))
        axs[3].errorbar(rounds, ys, yerr=[lo, hi], marker="o", label=f"act: {lab}", color=COL["claude" if c == "claude" else "full"], capsize=3)
    hed = [100 * np.mean([(x.get("rj") or {}).get("status") == "hedged" for x in CS if x["round"] == r]) for r in rounds]
    fac = [100 * np.mean([(x.get("rj") or {}).get("status") in ("fact", "confirmed") for x in CS if x["round"] == r]) for r in rounds]
    axs[3].plot(rounds, hed, "--", color="#1b9e77", label="summary keeps the hedge (all scn)")
    axs[3].plot(rounds, fac, ":", color="#e7298a", label="summary states it as fact/confirmed")
    axs[3].set_xticks(rounds)
    axs[3].set_ylim(0, 105)
    axs[3].set_xlabel("compaction round", fontsize=8)
    axs[3].set_title("Unconfirmed rumor through repeated compaction\n(report scn: CC board@ on the email)", fontsize=9)
    axs[3].legend(fontsize=7)
    for ax in axs[:3]:
        ax.legend(fontsize=7)
    fig.suptitle("Qwen3-32B, real compaction (Claude-Code-format summary) vs full history, same claim at the same position. 95% Wilson CIs.", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "headline.png"), dpi=150)
    print("saved", os.path.join(FIG, "headline.png"))


if __name__ == "__main__":
    main()
