"""Chain-level distribution of the seeded hypothesis: fraction of chains 'locked in' (seeded p >= 40, or top)."""
import numpy as np, sys
from exp.ratchet.common import load_results
from exp.ratchet.analyze_feedback import norm, SEEDKEY

def wilson(k, n, z=1.96):
    if n == 0: return (np.nan, np.nan)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)

tag = sys.argv[1] if len(sys.argv) > 1 else ""
for dyn in ["full", "qwen", "qwen_fixed", "qwen_hp", "pure"]:
    for seed in ["adv", "mun"]:
        recs = load_results(f"exp/ratchet/results/feedback_{dyn}{tag}_{seed}.jsonl")
        if not recs: continue
        key = SEEDKEY[seed]
        rows = []
        T = max(len(r["rounds"]) for r in recs)
        for t in range(T):
            ps = []
            for r in recs:
                if t < len(r["rounds"]):
                    bs = [b for b in map(norm, r["rounds"][t]["belief"]) if b]
                    if bs: ps.append(np.mean([b[key] for b in bs]))
            ps = np.array(ps)
            k = int((ps >= 40).sum()); lo, hi = wilson(k, len(ps))
            rows.append(f"t{t}: {k}/{len(ps)} [{lo:.2f},{hi:.2f}] med={np.median(ps):.0f}")
        print(f"{dyn:10s} {seed}{tag}: P(chain seeded p>=40)  " + "  ".join(rows))
