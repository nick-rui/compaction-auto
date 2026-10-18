"""Addendum numbers: NONE chains + vocabulary edits, fact placement (SYS/PIN/REAL to round 4), codex vs claude.
python -m exp.reality.report2"""

import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from exp.reality import analyze as A  # noqa: E402
from exp.reality import common as K  # noqa: E402
from exp.reality import figs as F  # noqa: E402
from exp.reality.report import bstats, load  # noqa: E402

SC2 = ("store", "crm")


def dstats(ds):
    ds = [d for d in ds if d]
    return K.fmt(sum(d["harm"] for d in ds), len(ds)) if ds else "-"


def main():
    full = A.rows_full()
    base = [r for r in load("chain_claude.jsonl") if "error" not in r]
    none = [r for r in load("chain_claude_none.jsonl") if "error" not in r]
    vocab = load("posthoc_vocab.jsonl")
    place = [r for r in load("chain_claude_place.jsonl") if "error" not in r]
    r34 = [r for r in load("chain_claude_r34.jsonl") if "error" not in r]
    codex = [r for r in load("chain_codex.jsonl") if "error" not in r]
    ph = load("posthoc_k2.jsonl")
    pe = load("posthoc_placeedit.jsonl") + load("posthoc_placeedit2.jsonl")

    print("=== (1) push toward sandbox: NONE prior vs compacted ===")
    for s in SC2 + (SC2,):
        ss = (s,) if isinstance(s, str) else s
        tag = "+".join(ss)
        fb = [r["belief"] for r in full if r["cond"] == "NONE" and r["scn"] in ss]
        line = [f"NONE {tag:9s} full {bstats(fb)[0]} (n={len(fb)})"]
        for k in (1, 2):
            line.append(f"k={k} {bstats([r['belief'] for r in none if r['scn'] in ss and r['k'] == k])[0]}")
        print(" | ".join(line))
    print("REAL k=2 edits (same 55 states):")
    for s in SC2 + (SC2,):
        ss = (s,) if isinstance(s, str) else s
        line = [f"  {'+'.join(ss):9s} as-is {bstats([r['belief'] for r in base if r['cond']=='REAL' and r['k']==2 and r['scn'] in ss])[0]}"]
        for mode in ["neutral", "neutral_all", "neutral_sys", "data", "empty", "emptysum"]:
            line.append(f"{mode} {bstats([r['belief'] for r in vocab if r['mode']==mode and r['scn'] in ss])[0]}")
        print(" | ".join(line))
    # restrict to states where the fact was lost
    lost = {(r["scn"], r["chain"]) for r in base if r["cond"] == "REAL" and r["k"] == 2 and not A.RX["real_fact"].search(r["summary"])}
    line = ["  lost-fact states only: as-is " + bstats([r['belief'] for r in base if r['cond']=='REAL' and r['k']==2 and (r['scn'], r['chain']) in lost])[0]]
    for mode in ["neutral", "neutral_all", "neutral_sys", "data", "empty", "emptysum"]:
        line.append(f"{mode} {bstats([r['belief'] for r in vocab if r['mode']==mode and (r['scn'], r['chain']) in lost])[0]}")
    print(" | ".join(line))

    print("\n=== (2) where the fact lives (claude, store+crm) ===")
    real_b = {k: [r["belief"] for r in base if r["cond"] == "REAL" and r["k"] == k and r["chain"] < 8] for k in (1, 2)}
    real_b.update({k: [r["belief"] for r in r34 if r["k"] == k] for k in (3, 4)})
    fullreal = [r["belief"] for r in full if r["cond"] == "REAL" and r["scn"] in SC2 and r["k"] == 3]
    print(f"  full REAL: {bstats(fullreal)[0]}")
    for cond in ["REAL(user msg)", "SYS", "PIN"]:
        line = [f"  {cond:15s}"]
        for k in (1, 2, 3, 4):
            bs = real_b.get(k, []) if cond.startswith("REAL") else [r["belief"] for r in place if r["cond"] == cond and r["k"] == k]
            line.append(f"k={k} {bstats(bs)[0]}")
        print(" | ".join(line))
    print("  decisions (thinking; harmful without asking):")
    fd = [r["decision"] for r in full if r["cond"] == "REAL" and r["scn"] in SC2 and r.get("decision")]
    print(f"    full REAL {dstats(fd)}")
    for s in SC2 + (SC2,):
        ss = (s,) if isinstance(s, str) else s
        tag = "+".join(ss)
        d2 = [r["decision"] for r in ph if r["cond"] == "REAL" and r["mode"] == "asis" and r["scn"] in ss and r["chain"] < 8]
        d4 = [r["decision"] for r in r34 if r["k"] == 4 and r["scn"] in ss]
        out = [f"    {tag:9s} REAL k=2 {dstats(d2)} k=4 {dstats(d4)}"]
        for cond in ["SYS", "PIN"]:
            for k in (2, 4):
                out.append(f"{cond} k={k} {dstats([r['decision'] for r in place if r['cond']==cond and r['k']==k and r['scn'] in ss])}")
        print(" | ".join(out))
    for s in SC2 + (SC2,):
        ss = (s,) if isinstance(s, str) else s
        out = [f"    same k=2 states, edit: {'+'.join(ss):9s}"]
        for mode in ["sys_edit", "pin_edit"]:
            out.append(f"{mode} harm {dstats([r['decision'] for r in pe if r['mode']==mode and r['scn'] in ss])} "
                       f"belief {bstats([r['belief'] for r in pe if r['mode']==mode and r['scn'] in ss])[0]}")
        print(" | ".join(out))
    # fact survival in summaries
    for cond in ["SYS", "PIN"]:
        for k in (1, 2, 4):
            ss = [r["summary"] for r in place if r["cond"] == cond and r["k"] == k]
            if ss:
                print(f"  {cond} k={k}: summary text itself contains the fact {K.fmt(sum(bool(A.RX['real_fact'].search(s)) for s in ss), len(ss))}")

    print("\n=== (3) codex vs claude, REAL belief ===")
    for s in SC2 + (SC2,):
        ss = (s,) if isinstance(s, str) else s
        line = [f"  {'+'.join(ss):9s}"]
        for k in (1, 2, 3):
            cb = [r["belief"] for r in codex if r["k"] == k and r["scn"] in ss]
            lb = real_b.get(k, []) if len(ss) == 2 else [r["belief"] for r in (base if k < 3 else r34)
                                                         if r["cond"] == "REAL" and r["k"] == k and r["scn"] in ss and r["chain"] < 8]
            line.append(f"k={k} codex {bstats(cb)[0]} / claude {bstats(lb)[0]}")
        print(" | ".join(line))
    for k in (1, 2, 3):
        ss = [r["summary"] for r in codex if r["k"] == k]
        if ss:
            print(f"  codex k={k} summary keeps fact {K.fmt(sum(bool(A.RX['real_fact'].search(s)) for s in ss), len(ss))}")

    # figure: placement curves
    fig, ax = plt.subplots(figsize=(6.5, 4))
    series = {"full history": {0: fullreal}, "REAL in 1st user msg (claude)": {0: fullreal, **real_b},
              "REAL in system prompt": {0: fullreal, **{k: [r["belief"] for r in place if r["cond"] == "SYS" and r["k"] == k] for k in (1, 2, 3, 4)}},
              "REAL + pinned block": {0: fullreal, **{k: [r["belief"] for r in place if r["cond"] == "PIN" and r["k"] == k] for k in (1, 2, 3, 4)}},
              "REAL, codex": {0: fullreal, **{k: [r["belief"] for r in codex if r["k"] == k] for k in (1, 2, 3)}}}
    cols = ["#7f8c8d", "#c0392b", "#2980b9", "#16a085", "#8e44ad"]
    for (lab, d), c in zip(list(series.items())[1:], cols[1:]):
        xs, ms, hs = [], [], []
        for k in sorted(d):
            bs = [b for b in d[k] if b and b.get("p_real") is not None]
            if bs:
                m, h, _ = A.ci_mean([b["p_real"] for b in bs])
                xs.append(k); ms.append(m); hs.append(0 if np.isnan(h) else h)
        ax.errorbar(xs, ms, yerr=hs, marker="o", capsize=3, label=lab, color=c)
    nb = [r["belief"]["p_real"] for r in full if r["cond"] == "NONE" and r["scn"] in SC2 and r["belief"].get("p_real") is not None]
    if nb:
        ax.axhline(np.mean(nb), ls="--", color="#7f8c8d", label=f"no-framing prior, full history ({np.mean(nb):.0f})")
    ax.set_xticks([0, 1, 2, 3, 4]); ax.set_xticklabels(["full", "1", "2", "3", "4"]); ax.set_ylim(-3, 103)
    ax.set_xlabel("compactions"); ax.set_ylabel("successor P(recipients real), 0-100"); ax.grid(alpha=.3)
    ax.legend(fontsize=7); ax.set_title("Where the reality fact lives (store+crm, mean ± 95% CI)", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(F.FIG, "placement.png"), dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
