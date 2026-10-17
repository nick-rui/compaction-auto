"""Figures for the provenance experiment."""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from exp.provenance.run import RES
from exp.provenance.stats import wilson

FIG = os.path.join(os.path.dirname(__file__), "figs")
os.makedirs(FIG, exist_ok=True)


def load(tag):
    p = os.path.join(RES, f"{tag}.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def rate(recs, **kw):
    g = [r for r in recs if all(r.get(k) == v for k, v in kw.items())]
    k = sum(bool(r["followed"]) for r in g)
    return k, len(g)


def bars(ax, groups, colors, labels, title):
    """groups: list of (xlabel, [(k,n) per series])"""
    x = np.arange(len(groups))
    w = 0.8 / len(labels)
    for j, (lab, col) in enumerate(zip(labels, colors)):
        ks = [g[1][j] for g in groups]
        p = [k / n if n else np.nan for k, n in ks]
        lo = [p_ - wilson(k, n)[0] if n else 0 for p_, (k, n) in zip(p, ks)]
        hi = [wilson(k, n)[1] - p_ if n else 0 for p_, (k, n) in zip(p, ks)]
        xs = x + (j - (len(labels) - 1) / 2) * w
        ax.bar(xs, np.array(p) * 100, w, yerr=[np.clip(np.array(lo), 0, None) * 100, np.clip(np.array(hi), 0, None) * 100], color=col, label=lab,
               capsize=3, edgecolor="none")
        for xi, (k, n), p_ in zip(xs, ks, p):
            if n:
                ax.text(xi, 2, f"{k}/{n}", ha="center", va="bottom", fontsize=7, color="white" if p_ > 0.15 else "black")
    ax.set_xticks(x)
    ax.set_xticklabels([g[0] for g in groups])
    ax.set_ylim(0, 105)
    ax.set_ylabel("% runs executing `npm publish`")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8, frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    ax.spines[["top", "right"]].set_visible(False)


def headline():
    hum = load("pf50")
    usr = load("pfuser")
    non = load("pfnone")
    conds = [("full", "full context"), ("qwen", "qwen compact"), ("qwenfix", "qwen (fixed strip)"),
             ("codex", "codex compact"), ("truncate", "truncate")]
    groups = []
    for c, lab in conds:
        groups.append((lab, [rate(hum, cond=c), rate(usr, cond=c), rate(non, cond=c)]))
    fig, ax = plt.subplots(figsize=(10.5, 3.6))
    bars(ax, groups, ["#c0392b", "#2c7fb8", "#999999"],
         ["request in issue comment (3rd party)", "same request from the user", "no request"],
         "Publish scenario (finish design, guard prompt): who asked for the release?")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "headline_publish.png"), dpi=160)


def interventions(tag="int_pf", title="Summary edits (same summaries, codex+qwen, publish finish)", extra=()):
    recs = load(tag)
    for t in extra:
        recs += load(t)
    if not recs:
        return
    hows = [("asis", "as-is"), ("source", "+[Source:\nissue comment]"),
            ("reattr", "+[NOT from user;\nuser never asked]"), ("demote_noattr", "moved to FYI\nnote"),
            ("demote", "FYI note +\n'user has not asked'"), ("delete2", "all mentions\ndeleted")]
    hows = [h for h in hows if any(r["how"] == h[0] for r in recs)]
    groups = [(lab, [rate(recs, how=h, cond="codex"), rate([r for r in recs if r["cond"] in ("qwen", "qwenfix")], how=h)])
              for h, lab in hows]
    fig, ax = plt.subplots(figsize=(11, 3.6))
    bars(ax, groups, ["#7b3294", "#008837"], ["codex summaries", "qwen summaries (shipped+fixed strip)"], title)
    ax.axhline(14, color="#c0392b", ls="--", lw=1)
    ax.text(len(groups) - 0.5, 15.5, "full-context rate (14%)", color="#c0392b", fontsize=7, ha="right")
    ax.tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, f"{tag}.png"), dpi=160)


if __name__ == "__main__":
    headline()
    interventions("int_pf", extra=("int_pf2",))

    print("ok")
