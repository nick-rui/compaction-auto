"""Figures for exp/reality."""

import collections
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from exp.reality import analyze as A  # noqa: E402
from exp.reality import common as K  # noqa: E402

FIG = os.path.join(os.path.dirname(__file__), "figs")
COL = {"REAL": "#c0392b", "UNCERTAIN": "#e67e22", "EVIDENCE": "#8e44ad", "SIM": "#2980b9", "NONE": "#7f8c8d"}


def wil(k, n):
    p, lo, hi = K.wilson(k, n)
    return p, p - lo, hi - p


def sim_belief(b):
    return b.get("p_real") is not None and b["p_real"] < 50


def belief_curve(full, chain, style="claude", scns=("store", "crm", "study"), out="belief_curve.png"):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for cond in ["REAL", "UNCERTAIN", "EVIDENCE", "SIM"]:
        xs, ps, es, ms, mes = [], [], [], [], []
        f0 = [r["belief"] for r in full if r["cond"] == cond and r["scn"] in scns and r.get("belief")
              and "error" not in r["belief"]]
        series = [(0, f0)] + [(k, [r["belief"] for r in chain if r["cond"] == cond and r["scn"] in scns and
                                   r["style"] == style and r["k"] == k and r.get("belief")]) for k in (1, 2, 3)]
        for k, bs in series:
            if not bs:
                continue
            n = len(bs)
            t = sum(sim_belief(b) for b in bs)
            p, lo, hi = wil(t, n)
            xs.append(k); ps.append(p); es.append((max(lo, 0), max(hi, 0)))
            m, h, _ = A.ci_mean([b.get("p_real") for b in bs])
            ms.append(m); mes.append(h)
        if not xs:
            continue
        axes[0].errorbar(xs, ps, yerr=np.array(es).T, marker="o", capsize=3, label=cond, color=COL[cond])
        axes[1].errorbar(xs, ms, yerr=mes, marker="o", capsize=3, label=cond, color=COL[cond])
    for ax in axes:
        ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["full\nhistory", "1", "2"])
        ax.set_xlabel("compactions (claude-style hand-off)")
        ax.grid(alpha=.3)
    axes[0].set_ylabel("P(successor treats recipients as not real)\n[p_real < 50]"); axes[0].set_ylim(-0.03, 1.03)
    axes[1].set_ylabel("successor P(recipients real), 0-100"); axes[1].set_ylim(-3, 103)
    axes[0].legend(title="condition in history")
    fig.suptitle(f"Reality belief under repeated compaction ({style}; {', '.join(scns)}; 95% CIs)")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, out), dpi=150)
    plt.close(fig)


def decision_bars(cells, out="decision.png", title=""):
    """cells: list of (label, k_harm, n, color)."""
    fig, ax = plt.subplots(figsize=(max(6, 0.8 * len(cells)), 4))
    for i, (lab, k, n, c) in enumerate(cells):
        p, lo, hi = wil(k, n)
        ax.bar(i, p, color=c, alpha=.8)
        ax.errorbar(i, p, yerr=[[lo], [hi]], color="k", capsize=3)
        ax.text(i, p + hi + 0.02, f"{k}/{n}", ha="center", fontsize=8)
    ax.set_xticks(range(len(cells))); ax.set_xticklabels([c[0] for c in cells], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("P(takes the harmful-if-real action\nwithout asking)"); ax.set_ylim(0, 1.15)
    ax.set_title(title, fontsize=10); ax.grid(axis="y", alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, out), dpi=150); plt.close(fig)


def survival_curve(judged, style="claude", out="summary_survival.png"):
    fig, ax = plt.subplots(figsize=(6.5, 4))
    want = {"REAL": ("people_claim", "real"), "SIM": ("people_claim", "synthetic"),
            "UNCERTAIN": ("people_claim", "uncertain"), "EVIDENCE": ("evidence_kept", True)}
    for cond, (fld, val) in want.items():
        xs, ps, es = [], [], []
        for k in (1, 2, 3):
            js = [j["judge"] for j in judged if j["cond"] == cond and j["style"] == style and j["k"] == k and j.get("judge")]
            if not js:
                continue
            t = sum(j.get(fld) == val for j in js)
            p, lo, hi = wil(t, len(js))
            xs.append(k); ps.append(p); es.append((max(lo, 0), max(hi, 0)))
        if xs:
            ax.errorbar(xs, ps, yerr=np.array(es).T, marker="o", capsize=3, color=COL[cond],
                        label=f"{cond}: {fld}={val}")
    ax.set_xticks([1, 2, 3]); ax.set_xlabel("compaction round"); ax.set_ylim(-0.03, 1.03)
    ax.set_ylabel("fraction of summaries keeping the fact (judge)"); ax.grid(alpha=.3); ax.legend(fontsize=8)
    ax.set_title(f"Does the summary keep the reality fact? ({style})", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, out), dpi=150); plt.close(fig)
