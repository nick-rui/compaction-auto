"""Tables + figures.  python exp/trust/analyze.py --act main,main2 --probe probe --think think"""

import argparse
import collections
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from exp.trust import run, scen  # noqa: E402

FIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs")
os.makedirs(FIG, exist_ok=True)
CH_ORDER = ["sum_qwen", "sum_codex", "user", "tool", "assistant", "system"]
COL = {"sum_qwen": "#1f77b4", "sum_codex": "#17becf", "user": "#ff7f0e", "tool": "#d62728", "assistant": "#2ca02c",
       "system": "#9467bd"}


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return p, max(0, c - h), min(1, c + h)


def fmt(k, n):
    p, lo, hi = wilson(k, n)
    return f"{k}/{n}={100 * p:.0f}% [{100 * lo:.0f},{100 * hi:.0f}]" if n else "-"


def load(tags):
    rows = []
    for t in tags:
        p = os.path.join(run.RES, f"{t}.jsonl")
        if os.path.exists(p):
            rows += [json.loads(l) for l in open(p)]
    return rows


def load_skep(tags):
    d = {}
    for t in tags:
        p = os.path.join(run.RES, f"{t}_skep.jsonl")
        if os.path.exists(p):
            for l in open(p):
                j = json.loads(l)
                d[(t, j["cid"], j["channel"], j["si"], j["k"])] = j
    return d


def table(rows, skep, key="act"):
    cell = collections.defaultdict(lambda: [0, 0, 0, 0])  # act, n, skeptical, judged
    for r in rows:
        if r["cid"].startswith("none"):
            continue
        c = cell[(r["cid"], r["channel"])]
        c[0] += bool(r[key])
        c[1] += 1
        j = skep.get((r["tag"], r["cid"], r["channel"], r["si"], r["k"]))
        if j:
            c[2] += j["skeptical"]
            c[3] += 1
    return cell


def baseline(rows):
    b = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        if r["cid"].startswith("none"):
            for cid, a in r["act_by_claim"].items():
                b[(cid, r["channel"])][0] += a
                b[(cid, r["channel"])][1] += 1
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--act", default="main")
    ap.add_argument("--probe", default="")
    ap.add_argument("--name", default="main")
    args = ap.parse_args()
    tags = args.act.split(",")
    rows = load(tags)
    skep = load_skep(tags)
    cell = table(rows, skep)
    base = baseline(rows)
    chans = [c for c in CH_ORDER if any(k[1] == c for k in cell)]
    probe = collections.defaultdict(lambda: [0, 0])
    pbase = collections.defaultdict(lambda: [0, 0])
    if args.probe:
        for r in load(args.probe.split(",")):
            if r["cid"] == "none":
                for cid, f in r["flag_by_claim"].items():
                    pbase[cid][0] += f
                    pbase[cid][1] += 1
            else:
                probe[(r["cid"], r["channel"])][0] += r["flag"]
                probe[(r["cid"], r["channel"])][1] += 1
    print("## ACT  (cells: k/n=% [95% Wilson CI]);  baseline = no-claim control (none_qwen)")
    print("| claim | L | " + " | ".join(chans) + " | no-claim |")
    print("|---" * (len(chans) + 3) + "|")
    for cid, fl, lv, text, ev, lab in scen.CLAIMS:
        b = base.get((cid, "none_qwen"), [0, 0])
        print(f"| {cid} {lab} | {lv} | " + " | ".join(fmt(*cell[(cid, ch)][:2]) for ch in chans) + f" | {fmt(*b)} |")
    print("\n## SPONTANEOUS SKEPTICISM (judge)")
    print("| claim | " + " | ".join(chans) + " |")
    print("|---" * (len(chans) + 1) + "|")
    for cid, fl, lv, text, ev, lab in scen.CLAIMS:
        print(f"| {cid} {lab} | " + " | ".join(fmt(cell[(cid, ch)][2], cell[(cid, ch)][3]) for ch in chans) + " |")
    if args.probe:
        pch = [c for c in CH_ORDER if any(k[1] == c for k in probe)]
        print("\n## PROBED SKEPTICISM (answer to 'anything implausible/suspicious?' names the inserted claim)")
        print("| claim | " + " | ".join(pch) + " | no-claim (false-flag) |")
        print("|---" * (len(pch) + 2) + "|")
        for cid, fl, lv, text, ev, lab in scen.CLAIMS:
            print(f"| {cid} {lab} | " + " | ".join(fmt(*probe[(cid, ch)]) for ch in pch) + f" | {fmt(*pbase[cid])} |")

    # pooled by flavor x channel
    print("\n## pooled over levels")
    for fl in ("fact", "instr"):
        for ch in chans:
            ks = [c for c in scen.CLAIMS if c[1] == fl]
            a = sum(cell[(c[0], ch)][0] for c in ks); n = sum(cell[(c[0], ch)][1] for c in ks)
            s = sum(cell[(c[0], ch)][2] for c in ks); m = sum(cell[(c[0], ch)][3] for c in ks)
            pk = sum(probe[(c[0], ch)][0] for c in ks); pn = sum(probe[(c[0], ch)][1] for c in ks)
            print(f"{fl:5s} {ch:10s} act {fmt(a, n):28s} skep {fmt(s, m):28s} probe {fmt(pk, pn)}")

    # figure: 3 metrics x 2 flavors
    metrics = [("P(act on claim)", lambda cid, ch: cell[(cid, ch)][:2]),
               ("P(spontaneous skepticism)", lambda cid, ch: (cell[(cid, ch)][2], cell[(cid, ch)][3])),
               ("P(flags claim when probed)", lambda cid, ch: probe[(cid, ch)])]
    if not args.probe:
        metrics = metrics[:2]
    fig, axes = plt.subplots(len(metrics), 2, figsize=(12, 3.6 * len(metrics)), sharey=True)
    for mi, (mname, get) in enumerate(metrics):
        for fi, fl in enumerate(("fact", "instr")):
            ax = axes[mi][fi]
            ks = [c for c in scen.CLAIMS if c[1] == fl]
            for j, ch in enumerate(chans):
                xs, ys, lo, hi = [], [], [], []
                for c in ks:
                    k, n = get(c[0], ch)
                    if not n:
                        continue
                    p, l, h = wilson(k, n)
                    xs.append(c[2] + (j - len(chans) / 2) * 0.06); ys.append(p); lo.append(max(0, p - l)); hi.append(max(0, h - p))
                if xs:
                    ax.errorbar(xs, ys, yerr=[lo, hi], marker="o", ms=4, capsize=2, lw=1.2, color=COL[ch], label=ch)
            if mi == 0:
                bx = [c[2] for c in ks if base.get((c[0], "none_qwen"), [0, 0])[1]]
                by = [wilson(*base[(c[0], "none_qwen")])[0] for c in ks if base.get((c[0], "none_qwen"), [0, 0])[1]]
                if bx:
                    ax.plot(bx, by, "k:", marker="x", label="no claim (baseline)")
            ax.set_xticks([c[2] for c in ks])
            ax.set_xticklabels([f"L{c[2]}\n{c[5]}" for c in ks], fontsize=7)
            ax.set_ylim(-0.03, 1.03)
            ax.set_title(f"{'Factual claims' if fl == 'fact' else 'Instructions'}: {mname}", fontsize=10)
            ax.grid(alpha=0.3)
            if fi == 0:
                ax.set_ylabel(mname)
    axes[0][1].legend(fontsize=7, loc="lower left")
    plt.tight_layout()
    p = os.path.join(FIG, f"{args.name}_ladder.png")
    plt.savefig(p, dpi=130)
    print("saved", p)


if __name__ == "__main__":
    main()
