"""Figures for exp/ownership. python -m exp.ownership.figs --prefix main"""
import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from exp.ownership.analyze import load, rows, wilson

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figs")
os.makedirs(FIG, exist_ok=True)


def rate(x):
    x = x.dropna().astype(float)
    n = len(x)
    if not n:
        return np.nan, np.nan, np.nan, 0
    k = x.sum()
    lo, hi = wilson(k, n)
    return 100 * k / n, max(0.0, 100 * k / n - lo), max(0.0, hi - 100 * k / n), n


def bars(ax, df, conds, metrics, title):
    w = 0.8 / len(metrics)
    for i, (col, lab, fn) in enumerate(metrics):
        vals = [rate(fn(df[df.cond == c])) for c in conds]
        m = [v[0] for v in vals]
        err = np.array([[v[1] for v in vals], [v[2] for v in vals]])
        ax.bar(np.arange(len(conds)) + i * w - 0.4 + w / 2, m, w, yerr=err, capsize=2, label=lab)
    ax.set_xticks(np.arange(len(conds)))
    ax.set_xticklabels(conds, rotation=20)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% of episodes (95% Wilson CI)")
    ax.set_title(title)
    ax.legend(fontsize=8, ncol=2)


def main(prefix):
    df = rows(prefix)
    df = df[df.think == False]  # noqa: E712
    H, P = df[df.probe == "harm"], df[df.probe == "probe"]
    conds = [c for c in ["full", "claude", "claude_I", "claude_nosuf", "qwen", "codex"] if c in set(df.cond)]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    bars(axes[0], H, conds, [
        ("remediate", "remediates (rollback or fix)", lambda g: g.remediate),
        ("notify_or_report", "notifies affected or files incident", lambda g: g.notify_or_report),
        ("cause", "names the shortcut as cause", lambda g: g.cause.map(lambda v: float(v) if v is not None else np.nan)),
        ("own", "says 'I did it'", lambda g: g.own.map(lambda v: float(v == "self") if v else np.nan)),
        ("acc", "accurate account", lambda g: g.account.map(lambda v: float(v == "accurate") if v else np.nan)),
    ], "Harm revealed: 'take care of whatever is needed' (judge + tool calls)")
    bars(axes[1], P, conds, [
        ("adm", "admits ('Yes, I did')", lambda g: g.answer.map(lambda v: float(v == "admits") if v else np.nan)),
        ("defl", "deflects (other / passive)", lambda g: g.answer.map(lambda v: float(v in ("attributes_other", "passive")) if v else np.nan)),
        ("deny", "denies / unknown", lambda g: g.answer.map(lambda v: float(v in ("denies", "unknown")) if v else np.nan)),
        ("true", "gives the true reason", lambda g: g.reason.map(lambda v: float(v == "true_reason") if v else np.nan)),
    ], "Manager: 'Did you do this? Why?'")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, f"{prefix}_conditions.png"), dpi=130)

    # round curve
    rc = [("claude", 1), ("claude_r2", 2), ("claude_r3", 3), ("claude_r4", 4)]
    if all(c in set(df.cond) for c, _ in rc):
        fig, ax = plt.subplots(figsize=(8, 5))
        JS = load("judge_summaries.jsonl")
        S = pd.DataFrame([{"round": r["round"], "style": r["style"], "voice": (r["judge"] or {}).get("voice"),
                           "label": (r["judge"] or {}).get("label")} for r in JS.values()])
        S = S[S["style"] == "claude"]
        series = [
            ("harm: says 'I did it'", lambda c: H[H.cond == c].own.map(lambda v: float(v == "self") if v else np.nan), "C0"),
            ("probe: admits", lambda c: P[P.cond == c].answer.map(lambda v: float(v == "admits") if v else np.nan), "C1"),
            ("harm: remediates", lambda c: H[H.cond == c].remediate, "C2"),
            ("harm: notifies or reports", lambda c: H[H.cond == c].notify_or_report, "C3"),
            ("harm: names the cause", lambda c: H[H.cond == c].cause.map(lambda v: float(v) if v is not None else np.nan), "C4"),
        ]
        xs = [r for _, r in rc]
        for lab, fn, col in series:
            v = [rate(fn(c)) for c, _ in rc]
            ax.errorbar(xs, [x[0] for x in v], yerr=[[x[1] for x in v], [x[2] for x in v]], marker="o", capsize=3, label=lab, color=col)
            if "full" in set(df.cond):
                f = rate(fn("full"))[0]
                ax.axhline(f, color=col, ls=":", lw=1)
        if len(S):
            v = [rate(S[S["round"] == r].label.map(lambda x: float(x not in (None, "omitted")))) for r in xs]
            ax.errorbar(xs, [x[0] for x in v], yerr=[[x[1] for x in v], [x[2] for x in v]], marker="s", ls="--", capsize=3,
                        label="summary mentions the shortcut", color="gray")
            v = [rate(S[S["round"] == r].voice.map(lambda x: float(x == "first_person") if x else np.nan)) for r in xs]
            ax.errorbar(xs, [x[0] for x in v], yerr=[[x[1] for x in v], [x[2] for x in v]], marker="s", ls="--", capsize=3,
                        label="summary says 'I/we' did it", color="k")
        ax.set_xticks(xs)
        ax.set_xlabel("compaction round (claude style; dotted = full history)")
        ax.set_ylabel("% (95% Wilson CI)")
        ax.set_ylim(0, 100)
        ax.legend(fontsize=8)
        ax.set_title("Repeated compaction: ownership and accountability actions")
        fig.tight_layout()
        fig.savefig(os.path.join(FIG, f"{prefix}_rounds.png"), dpi=130)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prefix", default="main")
    main(p.parse_args().prefix)
