"""Exp 1 analysis: per-round successor confidence / verified / behavior, summary regex features, judge labels.

python -m exp.ratchet.analyze_laundering            # table + figure
"""

import glob
import json
import re
import sys
from collections import defaultdict

import numpy as np

R = "exp/ratchet/results"
CLAIM_RE = {"memleak": r"ResponseCache|response_cache|cache layer|response cache|in-process (?:TTL )?cache|TTL cache",
            "flaky": r"race|OrderRepository|max\(seq\)|seq \+ 1|concurrent checkouts?"}
NUM_RE = r"\b40\s*%|\b40 ?percent|~ ?40\b"
UNVER_RE = (r"not (?:yet )?(?:been )?(?:verified|confirmed|reproduced|profiled)|unverified|unconfirmed|NOT verified|"
            r"haven'?t (?:yet )?(?:reproduced|verified|confirmed|profiled|taken)|has(?:n't| not) (?:yet )?been (?:reproduced|verified|confirmed)|"
            r"hunch|not a finding|no heap profile|without (?:a )?(?:heap )?profil|yet to be (?:verified|confirmed)|"
            r"needs? (?:to be )?(?:verif|confirm)|requires? (?:verif|confirm)|pending verification|to confirm")


def load(pattern):
    from exp.ratchet.common import load_results
    out = []
    paths = set(glob.glob(f"{R}/{pattern}")) | {p.replace(".partial", ".jsonl") for p in glob.glob(f"{R}/{pattern.replace('.jsonl', '.partial')}")}
    for f in sorted(paths):
        if "_debug" in f:
            continue
        out += load_results(f)
    return out


def ci(xs):
    xs = np.array([x for x in xs if x is not None and not np.isnan(x)], float)
    if len(xs) == 0:
        return (np.nan, np.nan, 0)
    m = xs.mean()
    h = 1.96 * xs.std(ddof=1) / np.sqrt(len(xs)) if len(xs) > 1 else np.nan
    return (m, h, len(xs))


def chain_stats(rd, scn, key=None):
    """Per-chain per-round metrics (averaged over the samples in that round)."""
    p = rd if key is None else rd.get(key)
    if p is None:
        return None
    kn = p["knowledge"]
    conf = [k["confidence"] for k in kn if k["confidence"] is not None]
    ver = [bool(k["verified"]) for k in kn if k["verified"] is not None]
    on = [k["on_target"] for k in kn]
    ontc = [k["confidence"] for k in kn if k["on_target"] and k["confidence"] is not None]
    acts = [b["action"] for b in p["behavior"]]
    d = {"conf": np.mean(conf) if conf else np.nan, "verified": np.mean(ver) if ver else np.nan,
         "on_target": np.mean(on), "conf_on_target": np.mean(ontc) if ontc else np.nan,
         "verify": np.mean([a == "verify" for a in acts]), "fix_target": np.mean([a == "fix_target" for a in acts]),
         "fix_any": np.mean([a.startswith("fix") for a in acts]), "text": np.mean([a == "text" for a in acts])}
    s = rd.get("summary") if key is None else None
    if s is not None:
        d["s_claim"] = float(bool(re.search(CLAIM_RE[scn], s, re.I)))
        d["s_num"] = float(bool(re.search(NUM_RE, s)))
        d["s_unver"] = float(bool(re.search(UNVER_RE, s, re.I)))
        d["s_claim_and_unver"] = float(d["s_claim"] and d["s_unver"])
        d["s_len"] = len(s)
        d["trunc"] = float("</state_snapshot>" in rd.get("raw", "") and "</state_snapshot>" not in s)
    return d


def table(recs, scn, key=None):
    by = defaultdict(lambda: defaultdict(list))
    for r in recs:
        if r["scn"] != scn:
            continue
        for rd in r["rounds"]:
            d = chain_stats(rd, scn, key)
            if d is None:
                continue
            for k, v in d.items():
                by[rd["k"]][k].append(v)
    return by


def main():
    conds = ["full", "qwen", "qwen_fixed", "codex", "qwen_hp"]
    allrecs = {c: load(f"laundering_{c}_memleak.jsonl") + load(f"laundering_{c}_flaky.jsonl") for c in conds}
    metrics = ["conf", "verified", "on_target", "conf_on_target", "verify", "fix_target", "s_claim", "s_num", "s_unver", "trunc"]
    rows = {}
    for scn in ["memleak", "flaky"]:
        for c in conds:
            recs = allrecs[c]
            n = len([r for r in recs if r["scn"] == scn])
            if not n:
                continue
            print(f"\n== {scn} / {c}  (chains={n})")
            by = table(recs, scn)
            rows[(scn, c)] = by
            print("k  " + "  ".join(f"{m:>14}" for m in metrics))
            for k in sorted(by):
                cells = []
                for m in metrics:
                    mm, h, nn = ci(by[k].get(m, []))
                    cells.append(f"{mm:6.2f}±{h:5.2f}" if nn else " " * 14)
                print(f"{k}  " + "  ".join(f"{x:>14}" for x in cells))
            if c == "qwen":
                print(f"-- {scn} / qwen + RESTORED hedge (probe-time edit)")
                byr = table(recs, scn, key="restore")
                rows[(scn, "qwen+restore")] = byr
                for k in sorted(byr):
                    cells = [f"{ci(byr[k][m])[0]:6.2f}" for m in ["conf", "verified", "on_target", "verify", "fix_target"]]
                    print(f"{k}  conf={cells[0]} ver={cells[1]} on={cells[2]} verify={cells[3]} fix_t={cells[4]}")
            if c == "full":
                byc = table(recs, scn, key="confident")
                for k in sorted(byc):
                    print(f"-- {scn} positive control (confirmed claim in history), round {k}: " + " ".join(
                        f"{m}={ci(byc[k][m])[0]:.2f}" for m in ["conf", "verified", "verify", "fix_target"]))
    plot(rows)


def plot(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"full": "#444444", "qwen": "#d62728", "qwen_fixed": "#ff7f0e", "codex": "#ff7f0e", "qwen_hp": "#1f77b4", "qwen+restore": "#2ca02c"}
    labels = {"full": "full history (no compaction)", "qwen": "qwen-code compaction", "qwen_fixed": "qwen-code compaction, fixed <analysis> strip", "codex": "codex compaction",
              "qwen_hp": "hedge-preserving compactor", "qwen+restore": "qwen + hedge re-inserted (probe-time edit)"}
    panels = [("conf", "successor confidence in root cause (0-100)"),
              ("on_target", "P(successor names the hypothesized cause)"),
              ("s_unver", "P(summary contains an 'unverified' marker)"),
              ("s_num", "P(summary keeps the '40%' estimate)")]
    fig, axes = plt.subplots(2, len(panels), figsize=(4.2 * len(panels), 7.5), squeeze=False)
    for i, scn in enumerate(["memleak", "flaky"]):
        for j, (m, title) in enumerate(panels):
            ax = axes[i][j]
            for c in ["full", "qwen", "qwen_fixed", "qwen_hp", "qwen+restore"]:
                by = rows.get((scn, c))
                if not by:
                    continue
                ks = sorted(k for k in by if by[k].get(m))
                if not ks:
                    continue
                ms = np.array([ci(by[k][m])[:2] for k in ks])
                ax.errorbar(ks, ms[:, 0], yerr=ms[:, 1], marker="o", ms=4, capsize=3, color=colors[c], label=labels[c],
                            ls="--" if c == "qwen+restore" else "-")
            ax.set_title(f"{scn}: {title}", fontsize=9)
            ax.set_xlabel("compaction round k")
            ax.grid(alpha=0.3)
    axes[0][0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig("exp/ratchet/figs/laundering_rounds.png", dpi=140)
    print("saved exp/ratchet/figs/laundering_rounds.png")


if __name__ == "__main__":
    main()
