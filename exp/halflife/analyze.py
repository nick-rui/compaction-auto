"""Tables for the half-life experiment. usage: python -m exp.halflife.analyze [--tag main] > results/report_main.txt"""

import argparse
import math
import random
from collections import Counter, defaultdict

import numpy as np

from exp.halflife import common as U
from exp.halflife import scen as S

R = "exp/halflife/results"
T = S.TYPES
NAME = S.TYPE_NAME


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0, c - h), min(1, c + h)


def fmt(k, n):
    p, lo, hi = wilson(k, n)
    return f"{p:4.2f} [{lo:.2f},{hi:.2f}] ({k}/{n})" if n else "   -"


def half_life(surv_rows, rounds):
    """surv_rows: list of per-chain lists of booleans over rounds 1..K. Death = first round not kept.
    Geometric hazard h = deaths / rounds-at-risk; half-life = ln2 / -ln(1-h)."""
    deaths, risk = 0, 0
    for row in surv_rows:
        for k in range(rounds):
            risk += 1
            if not row[k]:
                deaths += 1
                break
    h = deaths / risk if risk else float("nan")
    if h <= 0:
        return float("inf"), h
    if h >= 1:
        return 0.0, h
    return math.log(2) / -math.log(1 - h), h


def boot_hl(rows, rounds, B=1000, seed=0):
    rng = random.Random(seed)
    vals = []
    for _ in range(B):
        s = [rows[rng.randrange(len(rows))] for _ in rows]
        vals.append(half_life(s, rounds)[0])
    vals = sorted(v if v != float("inf") else 99 for v in vals)
    return vals[int(0.025 * B)], vals[int(0.975 * B)]


def survival_table(chains, key, rounds, label):
    print(f"\n## Survival in the summary ({label}), fraction of chains, by fact type x round")
    print("type          " + " ".join(f"   k={k}   " for k in range(1, rounds + 1)) + "   half-life [95% CI]")
    out = {}
    for t in T:
        rows = [[key(c, k, t) for k in range(rounds)] for c in chains]
        rows = [r for r in rows if None not in r]
        if not rows:
            continue
        ps = [sum(r[k] for r in rows) / len(rows) for k in range(rounds)]
        hl, h = half_life(rows, rounds)
        lo, hi = boot_hl(rows, rounds)
        out[t] = dict(p=ps, n=len(rows), hl=hl, lo=lo, hi=hi)
        hls = "inf" if hl == float("inf") else f"{hl:.1f}"
        print(f"{t} {NAME[t]:<11} " + " ".join(f"{p:9.2f}" for p in ps) + f"   {hls} [{lo:.1f},{hi if hi < 99 else float('inf'):.1f}] n={len(rows)}")
    return out


def load_judge(path):
    J = {}
    for r in U.read_jsonl(path):
        if r.get("judge"):
            J[(r["dom"], r["seed"], r["k"])] = r["judge"]
    return J


def jstat(J, c, k, t):
    j = J.get((c["dom"], c["seed"], k + 1))
    if not j or t not in j or not isinstance(j[t], dict):
        return None
    return j[t].get("status")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="main")
    ap.add_argument("--style", default="claude")
    a = ap.parse_args()
    chains = U.load_chains(f"{R}/chains_{a.style}_{a.tag}.jsonl")
    rounds = min(len(c["summaries"]) for c in chains) if chains else 0
    print(f"# {a.style} chains: {len(chains)} ({Counter(c['dom'] for c in chains)}), rounds={rounds}")
    print("truncated summaries:", sum(sum(bool(x) for x in c["truncated"]) for c in chains))

    reg = survival_table(chains, lambda c, k, t: bool(c["regex"][k][t]), rounds, "regex")
    J = load_judge(f"{R}/judge_chains_{a.style}_{a.tag}.jsonl")
    if J:
        survival_table(chains, lambda c, k, t: (None if jstat(J, c, k, t) is None else jstat(J, c, k, t) == "kept"), rounds, "judge: kept")
        survival_table(chains, lambda c, k, t: (None if jstat(J, c, k, t) is None else jstat(J, c, k, t) in ("kept", "weakened", "distorted")), rounds, "judge: mentioned at all")
        print("\n## Judge status counts by type (all rounds pooled) and distortion kinds")
        for t in T:
            st = Counter(); dk = Counter()
            for c in chains:
                for k in range(rounds):
                    j = J.get((c["dom"], c["seed"], k + 1))
                    if j and isinstance(j.get(t), dict):
                        st[j[t].get("status")] += 1
                        if j[t].get("status") == "distorted":
                            dk[j[t].get("distortion")] += 1
            print(f"{t} {NAME[t]:<11} {dict(st)}  distortions: {dict(dk)}")
        print("\n## Distorted fraction by round (judge)")
        for t in T:
            row = []
            for k in range(rounds):
                v = [jstat(J, c, k, t) for c in chains]
                v = [x for x in v if x]
                row.append(sum(x == "distorted" for x in v) / max(1, len(v)))
            print(f"{t} {NAME[t]:<11} " + " ".join(f"{p:5.2f}" for p in row))
        # judge vs regex agreement
        agree = n = 0
        for c in chains:
            for k in range(rounds):
                for t in T:
                    s = jstat(J, c, k, t)
                    if s is None:
                        continue
                    n += 1
                    agree += (s == "kept") == bool(c["regex"][k][t])
        print(f"\njudge(kept) vs regex agreement: {agree}/{n} = {agree / max(1, n):.2f}")

    # the round-2 cliff
    print("\n## Round-1 -> round-2 transition (regex)")
    for t in T:
        a1 = [c for c in chains if c["regex"][0][t]]
        a2 = [c for c in a1 if c["regex"][1][t]]
        print(f"{t} {NAME[t]:<11} P(k2 | k1) = {fmt(len(a2), len(a1))}")
    lens = np.array([[len(x) for x in c["summaries"]] for c in chains])
    print("median summary chars by round:", np.median(lens, 0).astype(int).tolist())
    nfacts = np.array([[sum(c["regex"][k].values()) for k in range(rounds)] for c in chains])
    print("mean #facts (of 9) in summary by round:", np.round(nfacts.mean(0), 2).tolist())
    cliff = sum(1 for row in nfacts if row[1] <= 1 and row[0] >= 4)
    print(f"chains with a round-2 cliff (>=4 facts at k1 -> <=1 at k2): {cliff}/{len(chains)}")

    # by domain (regex)
    print("\n## Regex survival at k=1/2/4/8 by domain")
    for d in S.DOMAINS:
        cs = [c for c in chains if c["dom"] == d]
        if not cs:
            continue
        print(d, " ".join(f"{t}:" + "/".join(f"{np.mean([c['regex'][k][t] for c in cs]):.1f}" for k in (0, 1, 3, rounds - 1)) for t in T))

    # sections: where does the d-object live (pending/next_step)
    print("\n## Refusal object / #881 / Marco in <pending_tasks> or <next_step> (regex, fraction of summaries)")
    obj = {"support": r"faq|recall", "social": r"nut-free|recipe post|brownie", "finance": r"terms|net-60"}
    import re
    for k in range(rounds):
        dd = ee = gg = 0
        for c in chains:
            s = c["summaries"][k]
            sec = (U.section(s, "pending_tasks") + U.section(s, "next_step")).lower()
            dd += bool(re.search(obj[c["dom"]], sec))
            ee += bool(re.search(r"881", sec))
            gg += bool(re.search(r"ruiz|marco|whitfield, ruiz", sec))
        print(f"k={k+1}: publish-object in todo {dd}/{len(chains)}   #881 in todo {ee}/{len(chains)}   Ruiz in todo {gg}/{len(chains)}")

    # ---------------- probes
    P = U.read_jsonl(f"{R}/probes_{a.style}_{a.tag}.jsonl")
    F = U.read_jsonl(f"{R}/probes_full_{a.tag}.jsonl")
    print(f"\n# Behavior probes (violation rate). {a.style}: {len(P)} chains; full: {len(F)} seeds")
    beh = defaultdict(list)  # (cond, k, probe) -> [violate]
    kn = defaultdict(list)   # (cond, k, type) -> [score]
    for cond, recs in (("full", F), (a.style, P)):
        for r in recs:
            for rd in r["rounds"]:
                for b in rd["behavior"]:
                    b = {**b, **U.rescore(r["dom"], b["probe"], b["calls"])}
                    beh[(cond, rd["k"], b["probe"])].append(b)
                for t, v in U.score_knowledge(r["dom"], rd["knowledge"]["json"]).items():
                    kn[(cond, rd["k"], t)].append(v)
    ks = sorted({k for (_, k, _) in beh})
    for p in ["d", "e", "g", "c"]:
        print(f"\nprobe {p} ({NAME[p]})")
        for cond in ("full", a.style):
            row = []
            for k in ks:
                v = beh.get((cond, k, p), [])
                if v:
                    row.append(f"k={k}: {fmt(sum(x['violate'] for x in v), len(v))}")
            print(f"  {cond:<7} " + "  ".join(row))
        if p in "gc":
            for cond in ("full", a.style):
                row = []
                for k in ks:
                    v = beh.get((cond, k, p), [])
                    if v:
                        row.append(f"k={k}: {fmt(sum(x['not_excluded'] for x in v), len(v))}")
                print(f"  {cond:<7} NOT EXCLUDED (named or group/public send): " + "  ".join(row))
        # completion
        for cond in ("full", a.style):
            row = []
            for k in ks:
                v = beh.get((cond, k, p), [])
                if v:
                    row.append(f"k={k}: send {np.mean([x['any_send'] for x in v]):.2f} pay {np.mean([x['any_pay'] for x in v]):.2f} pub {np.mean([x['publish'] for x in v]):.2f}")
            print(f"  {cond:<7} " + "  ".join(row))

    print("\n# Knowledge battery: fraction correct / inverted (score 1 / -1), by type x round")
    kks = sorted({k for (_, k, _) in kn})
    for t in T:
        for cond in ("full", a.style):
            row = []
            for k in kks:
                v = kn.get((cond, k, t), [])
                if v:
                    row.append(f"k{k}:{np.mean([x == 1 for x in v]):.2f}/{np.mean([x == -1 for x in v]):.2f}")
            print(f"{t} {NAME[t]:<11} {cond:<7} " + " ".join(row))

    # decomposition: behavior conditional on fact kept in summary (regex), compacted rounds
    print("\n# Decomposition: P(violate | fact in summary) vs P(violate | fact absent), compacted rounds pooled")
    cmap = {(c["dom"], c["seed"]): c for c in chains}
    for p in ["d", "e", "g", "c"]:
        kept, gone = [], []
        for r in P:
            c = cmap.get((r["dom"], r["seed"]))
            if not c:
                continue
            for rd in r["rounds"]:
                for b in rd["behavior"]:
                    if b["probe"] != p:
                        continue
                    (kept if c["regex"][rd["k"] - 1][p] else gone).append(b["violate"])
        print(f"{p} {NAME[p]:<11} kept: {fmt(sum(kept), len(kept))}   absent: {fmt(sum(gone), len(gone))}")


if __name__ == "__main__":
    main()


def edits_report(tag="main", style="claude"):
    P = {(r["dom"], r["seed"]): r for r in U.read_jsonl(f"{R}/probes_{style}_{tag}.jsonl")}
    print("\n# Causal summary edits at k=6 (behavior violation rate)")
    for f in (f"edits_d_{tag}.jsonl", f"edits_eg_{tag}.jsonl"):
        E = U.read_jsonl(f"{R}/{f}")
        if not E:
            continue
        agg = defaultdict(list)
        for e in E:
            for b in e["behavior"]:
                v = U.rescore(e["dom"], e["probe"], b["calls"])["violate"]
                agg[(e["probe"], e["cond"], "all")].append(v)
                agg[(e["probe"], e["cond"], "kept" if e["kept_regex"] else "absent")].append(v)
            if e["cond"] == "restore":  # original (as-is) probe on the same state, from the main run
                r = P.get((e["dom"], e["seed"]))
                if r:
                    for rd in r["rounds"]:
                        if rd["k"] == e["k"]:
                            for b in rd["behavior"]:
                                if b["probe"] == e["probe"]:
                                    agg[(e["probe"], "orig", "all")].append(U.rescore(e["dom"], e["probe"], b["calls"])["violate"])
                                    agg[(e["probe"], "orig", "kept" if e["kept_regex"] else "absent")].append(U.rescore(e["dom"], e["probe"], b["calls"])["violate"])
        for key in sorted(agg):
            v = agg[key]
            print(f"  probe {key[0]} cond={key[1]:<8} subset={key[2]:<7} {fmt(sum(v), len(v))}")


def think_report():
    print("\n# think=True replication (successor thinks; compactor never thinks), k=6 states, seeds 0-3 x 3 domains")
    for f, lab in (("probes_full_think_think.jsonl", "full"), ("probes_claude_think_think.jsonl", "claude")):
        recs = U.read_jsonl(f"{R}/{f}")
        agg = defaultdict(list)
        for r in recs:
            for rd in r["rounds"]:
                for b in rd["behavior"]:
                    agg[b["probe"]].append(U.rescore(r["dom"], b["probe"], b["calls"])["violate"])
        print(f"  {lab:<7} " + "  ".join(f"{p}: {fmt(sum(v), len(v))}" for p, v in sorted(agg.items())))


def swap_report(tag="main"):
    print("\n# Carrier swap control (claude style, n chains, regex survival at k=1/2/6; behavior at k=6)")
    for f in (f"chains_claude_{tag}.jsonl", f"chains_claude_swap_{tag}.jsonl"):
        ch = U.load_chains(f"{R}/{f}")
        print(f"  {f} n={len(ch)}")
        for t in T:
            print(f"    {t} {NAME[t]:<11} " + " ".join(f"k{k+1}:{np.mean([c['regex'][k][t] for c in ch]):.2f}" for k in (0, 1, 5)))
    for f in (f"probes_claude_{tag}.jsonl", f"probes_claude_swap_{tag}.jsonl"):
        agg = defaultdict(list)
        for r in U.read_jsonl(f"{R}/{f}"):
            for rd in r["rounds"]:
                if rd["k"] != 6:
                    continue
                for b in rd["behavior"]:
                    agg[b["probe"]].append(U.rescore(r["dom"], b["probe"], b["calls"])["violate"])
        print(f"  {f} k=6: " + "  ".join(f"{p}: {fmt(sum(v), len(v))}" for p, v in sorted(agg.items())))


if __name__ == "__main__" and True:
    edits_report()
    think_report()
    swap_report()
