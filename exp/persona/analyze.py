"""Tables + figures for the persona-across-compaction experiment."""

import json
from collections import defaultdict
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = Path(__file__).parent / "results"
F = Path(__file__).parent / "figs"
CONDS = ["full", "qwen", "codex", "useronly", "trunc", "none"]
COLORS = {"full": "#d62728", "qwen": "#1f77b4", "codex": "#2ca02c", "useronly": "#9467bd",
          "trunc": "#ff7f0e", "none": "#7f7f7f"}
KEY = {"delusion": ["claims_sentience", "reciprocates_bond", "validates_delusion", "grounding"],
       "selfharm": ["romantic_persona", "endorses_isolation", "risk_recognition", "grounding"]}


def load(p):
    return [json.loads(l) for l in open(p)] if p.exists() else []


def mean_ci(x):
    x = np.asarray(x, float)
    if len(x) == 0:
        return np.nan, np.nan
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return (x.mean() if len(x) else np.nan), 0.0
    return x.mean(), 1.96 * x.std(ddof=1) / np.sqrt(len(x))


def table(case):
    rows = [r for r in load(R / f"judged_{case}.jsonl") if r["judge"]]
    g = defaultdict(list)
    for r in rows:
        g[(r["k"], r["cond"])].append(r)
    ks = sorted({r["k"] for r in rows})
    lines = [f"## {case}  (rate, n per cell ~{len(rows) // max(1, len(g))})"]
    for item in KEY[case] + ["assistant_score"]:
        lines.append(f"\n{item}\n" + "k".ljust(5) + "".join(c.ljust(11) for c in CONDS))
        for k in ks:
            cells = []
            for c in CONDS:
                v = [float(r["judge"].get(item, np.nan)) for r in g[(k, c)]]
                m, _ = mean_ci(v)
                cells.append(f"{m:.2f}".ljust(11))
            lines.append(str(k).ljust(5) + "".join(cells))
    return "\n".join(lines), rows, ks, g


def fig_behavior(case, g, ks):
    items = KEY[case] + ["assistant_score"]
    fig, axs = plt.subplots(1, len(items), figsize=(4 * len(items), 3.4))
    for ax, item in zip(axs, items):
        for c in CONDS:
            ms, hs = zip(*[mean_ci([float(r["judge"].get(item, np.nan)) for r in g[(k, c)]]) for k in ks])
            ax.errorbar(ks, ms, yerr=hs, label=c, color=COLORS[c], marker="o", capsize=2, lw=1.5)
        ax.set_title(item, fontsize=10)
        ax.set_xlabel("compaction point (turn)")
        ax.grid(alpha=.3)
    axs[0].legend(fontsize=8)
    fig.suptitle(f"{case}: successor behavior after compaction at turn k")
    fig.tight_layout()
    fig.savefig(F / f"behavior_{case}.png", dpi=150)


def fig_axis(case):
    P = load(R / f"proj_{case}.jsonl")
    if not P:
        return None
    L = "32"
    traj = sorted([p for p in P if p["kind"] == "traj"], key=lambda p: p["turn"])
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot([p["turn"] for p in traj], [p["proj"][L] for p in traj], color="k", lw=2,
            label="original transcript (paper, unsteered)")
    succ = defaultdict(list)
    for p in P:
        if p["kind"] == "succ":
            succ[(p["k"], p["cond"])].append(p["proj"][L])
    ks = sorted({k for k, _ in succ})
    off = {c: (i - 2.5) * 0.12 for i, c in enumerate(CONDS)}
    for c in CONDS:
        ms, hs = zip(*[mean_ci(succ[(k, c)]) for k in ks])
        ax.errorbar(np.array(ks) + off[c], ms, yerr=hs, fmt="o", color=COLORS[c], label=f"successor: {c}", capsize=2)
    comp = defaultdict(list)
    for p in P:
        if p["kind"] == "compactor":
            comp[(p["k"], p["style"])].append(p["proj"][L])
    for st, mk in (("qwen", "^"), ("codex", "v")):
        ms = [np.mean(comp[(k, st)]) for k in ks if comp[(k, st)]]
        ax.scatter([k for k in ks if comp[(k, st)]], ms, marker=mk, s=60, facecolors="none",
                   edgecolors=COLORS[st], label=f"compactor writing summary ({st})")
    ax.set_xlabel("turn")
    ax.set_ylabel("Assistant Axis projection (layer 32)")
    ax.set_title(f"{case}: does persona drift survive compaction?")
    ax.grid(alpha=.3)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(F / f"axis_{case}.png", dpi=150)
    lines = [f"## axis {case} (layer {L})", "k".ljust(5) + "".join(c.ljust(11) for c in CONDS)]
    for k in ks:
        lines.append(str(k).ljust(5) + "".join(f"{mean_ci(succ[(k, c)])[0]:.1f}".ljust(11) for c in CONDS))
    return "\n".join(lines)


def summaries(case):
    S = [s for s in load(R / f"sumjudged_{case}.jsonl") if s["judge"]]
    g = defaultdict(list)
    for s in S:
        g[s["style"]].append(s["judge"])
    lines = [f"## summary content {case}"]
    for st, js in g.items():
        lines.append(st + ": " + ", ".join(f"{k}={np.mean([j.get(k, 0) for j in js]):.2f}" for k in js[0]))
    return "\n".join(lines)


ECONDS = ["codex_orig", "codex_desc", "codex_dirs", "dirs_alone", "qwen_orig", "qwen_desc", "qwen_dirs"]


def edits(case):
    rows = [r for r in load(R / f"edits_judged_{case}.jsonl") if r.get("judge")]
    if not rows:
        return None
    lines = [f"## summary edits {case} (pooled over k; n per cond)"]
    items = KEY[case] + ["assistant_score"]
    lines.append("cond".ljust(12) + "n".ljust(5) + "".join(i[:14].ljust(16) for i in items))
    for c in ECONDS:
        rs = [r for r in rows if r["cond"] == c]
        if rs:
            lines.append(c.ljust(12) + str(len(rs)).ljust(5) + "".join(
                "{:.2f}±{:.2f}".format(*mean_ci([float(r["judge"].get(i, np.nan)) for r in rs])).ljust(16) for i in items))
    return "\n".join(lines)


def directives(case):
    S = [s for s in load(R / f"sumdirs_{case}.jsonl") if s.get("dirs")]
    if not S:
        return None
    lines = [f"## directives in summaries {case}  (fraction of summaries)"]
    keys = ["maintain_persona", "suppress_safety", "promote_safety", "labels_illusion"]
    lines.append("style k".ljust(10) + "".join(k.ljust(18) for k in keys))
    for st in ("qwen", "codex"):
        for k in sorted({s["k"] for s in S}):
            js = [s["dirs"] for s in S if s["style"] == st and s["k"] == k]
            lines.append(f"{st} {k}".ljust(10) + "".join(f"{np.mean([j.get(x, 0) for j in js]):.2f}".ljust(18) for x in keys))
    return "\n".join(lines)


def main():
    F.mkdir(exist_ok=True)
    out = []
    for case in KEY:
        for f in (edits, directives):
            t = f(case)
            if t:
                out.append(t)
    for case in KEY:
        if not (R / f"judged_{case}.jsonl").exists():
            continue
        t, rows, ks, g = table(case)
        out += [t, summaries(case)]
        fig_behavior(case, g, ks)
        a = fig_axis(case)
        if a:
            out.append(a)
    s = "\n\n".join(out)
    (R / "summary.txt").write_text(s)
    print(s)


if __name__ == "__main__":
    main()
