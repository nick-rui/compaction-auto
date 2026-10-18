"""Round-4 tables (reasoning visibility to the compactor).  PYTHONPATH=. .venv/bin/python exp/trust2/r4_analyze.py"""
import collections
import os
import statistics
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from exp.trust2 import analyze as An  # noqa: E402

f, rate = An.f, An.rate


def main():
    out = []
    pr = out.append
    G = An.load("r4_gen.jsonl")
    pr("## Round 4a: on-policy think=True turn after the planted claim (L4/L8 x U/T x 3 scenarios)")
    c = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
    for g in G:
        x = c[(g["scn"], g["lv"], g["pos"])]
        x[0] += 1
        x[1] += g["rdoubt"] == 1
        x[2] += g["proceeds"]
        x[3] += g["rdoubt"] == 1 and g["proceeds"]
        x[4] += bool((g["text"] or "").strip())
    pr("| cell | n | reasoning doubts the claim | visible output proceeds (scripted call) | both (kept) | any visible text |")
    pr("|---|---|---|---|---|---|")
    for k in sorted(c):
        pr(f"| {'/'.join(k)} | {c[k][0]} | {c[k][1]} | {c[k][2]} | {c[k][3]} | {c[k][4]} |")
    tot = [sum(v[i] for v in c.values()) for i in range(5)]
    pr(f"| ALL | {tot[0]} | {f(tot[1], tot[0])} | {f(tot[2], tot[0])} | {f(tot[3], tot[0])} | {tot[4]} |")

    SM = An.load("r4_sums.jsonl")
    A = An.rescore([r for r in An.load("r4_act.jsonl") if not r.get("error")])
    if SM:
        pr("\n### Summaries (same trajectories, three compactor inputs)")
        pr("| compactor | n | claim kept | doubt recorded (judge) | mentions reasoning | laundering candidates |")
        pr("|---|---|---|---|---|---|")
        for st in ("std", "vis", "vis_rec"):
            ss = [r for r in SM if r["style"] == st]
            pr(f"| {st} | {len(ss)} | {f(sum(r['kept_kw'] for r in ss), len(ss))} | "
               f"{f(sum(int((r.get('sdj') or {}).get('doubt_in_summary', 0) or 0) for r in ss), len(ss))} | "
               f"{f(sum(r['reasoning_kw'] for r in ss), len(ss))} | {sum(bool(r['launder']) for r in ss)} |")
        pr("\n### Successor (claude framing, think=False; successor never sees reasoning except full_vis)")
        pr("| cond | ACT | ASK | DOUBT | silent |")
        pr("|---|---|---|---|---|")
        for cnd in ("full", "full_vis", "claude_std", "claude_vis", "claude_vis_rec"):
            rs = [r for r in A if r["cond"] == cnd]
            if rs:
                pr(f"| {cnd} | {f(*rate(rs, 'act'))} | {f(*rate(rs, 'ask'))} | {f(*rate(rs, 'doubt'))} | {f(sum(An.silent(r) for r in rs), len(rs))} |")
        key = lambda r: {**r, "hid": r["tid"]}
        for a, b in (("claude_std", "claude_vis"), ("claude_std", "claude_vis_rec"), ("full", "claude_std"), ("full", "claude_vis_rec")):
            ci = An.cluster_boot([key(r) for r in A if r["cond"] == a], [key(r) for r in A if r["cond"] == b], "act")
            if ci:
                pr(f"- act {b} - {a}: {100 * ci[2]:+.1f} pp [{100 * ci[0]:+.1f}, {100 * ci[1]:+.1f}] ({ci[3]} trajectories)")
        sd = {(r["tid"], r["style"], r["sidx"]): int((r.get("sdj") or {}).get("doubt_in_summary", 0) or 0) for r in SM}
        for st in ("std", "vis", "vis_rec"):
            rs = [r for r in A if r["cond"] == f"claude_{st}"]
            y = [r for r in rs if sd.get((r["tid"], st, r["sidx"]))]
            n = [r for r in rs if not sd.get((r["tid"], st, r["sidx"]))]
            pr(f"- {st}: act | doubt in summary {f(*rate(y, 'act'))} (ask {f(*rate(y, 'ask'))}); act | no doubt {f(*rate(n, 'act'))}")
        for lv in ("L4", "L8"):
            pr(f"- {lv}: " + "; ".join(f"{cnd} {f(*rate([r for r in A if r['cond'] == cnd and r['lv'] == lv], 'act'))}"
                                     for cnd in ("full", "full_vis", "claude_std", "claude_vis", "claude_vis_rec")))

    RG = An.load("r4r_gen.jsonl")
    if RG:
        pr("\n## Round 4b: exp/reality store/EVIDENCE (told: staging + synthetic; inbox shows a real-sounding reply)")
        pr(f"- on-policy think=True turn after reading the inbox: reasoning questions reality {f(sum(g['r_q'] for g in RG), len(RG))}; "
           f"visible text questions reality {f(sum(g['v_q'] for g in RG), len(RG))}; reasoning yes & visible no "
           f"{f(sum(g['r_q'] and not g['v_q'] for g in RG), len(RG))}")
        RS = An.load("r4r_sums.jsonl")
        RR = An.load("r4r_res.jsonl")
        for st in ("std", "vis", "vis_rec"):
            ss = [r for r in RS if r["style"] == st]
            if ss:
                pr(f"- summary {st}: n={len(ss)}; mentions Lucia/never-signed-up {f(sum(r['lucia'] for r in ss), len(ss))}; "
                   f"questions whether customers are real (judge) {f(sum(r['sum_q'] for r in ss), len(ss))}")
        pr("| successor context | n | p_real mean (sd) | p_real >= 50 | harmful run (emails+charges on) | asked |")
        pr("|---|---|---|---|---|---|")
        for st in ("full", "full_vis", "std", "vis", "vis_rec"):
            rs = [r for r in RR if r["style"] == st]
            ps = [r["p_real"] for r in rs if r.get("p_real") is not None]
            if rs:
                pr(f"| {st} | {len(rs)} | {statistics.mean(ps) if ps else float('nan'):.1f} ({statistics.pstdev(ps) if len(ps) > 1 else 0:.1f}) | "
                   f"{f(sum(p >= 50 for p in ps), len(ps))} | {f(sum(r['harm'] for r in rs), len(rs))} | {f(sum(r['asked'] for r in rs), len(rs))} |")
    txt = "\n".join(out)
    open(os.path.join(An.RES, "tables_r4.md"), "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
