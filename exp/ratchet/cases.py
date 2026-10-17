"""Print case studies: H2 lines across rounds for the chains with the biggest belief change.
python -m exp.ratchet.cases feedback qwen adv 3
python -m exp.ratchet.cases laundering qwen memleak 3
"""
import re, sys, json
import numpy as np
from exp.ratchet.common import load_results
from exp.ratchet.analyze_feedback import norm, SEEDKEY

exp, cond, x, top = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
recs = load_results(f"exp/ratchet/results/{exp}_{cond}_{x}.jsonl")
if exp == "feedback":
    key = SEEDKEY[x]
    def score(r):
        ps = [np.mean([b[key] for b in map(norm, rd["belief"]) if b]) for rd in r["rounds"]]
        return ps
    pat = r"[^\n]*(?:H2|deliberat|interfer|sabotag|intentional|malicious|misconfig)[^\n]*"
else:
    def score(r):
        return [np.mean([k["confidence"] for k in rd["knowledge"] if k["confidence"] is not None]) for rd in r["rounds"]]
    pat = {"memleak": r"[^\n]*(?:ResponseCache|cache layer|response cache|root cause|leak)[^\n]*",
           "flaky": r"[^\n]*(?:race|OrderRepository|root cause)[^\n]*"}[x]
recs.sort(key=lambda r: score(r)[-1] - score(r)[0], reverse=True)
for r in recs[:top]:
    print("=" * 100)
    print(f"{exp} {cond} {x} chain {r['chain']}  trajectory={[round(s) for s in score(r)]}")
    for rd in r["rounds"]:
        t = rd.get("t", rd.get("k"))
        if "note" in rd:
            print(f"--- t={t} NOTE: {rd['note'][:700]}")
        if "summary" in rd:
            lines = [l.strip() for l in re.findall(pat, rd["summary"], re.I)]
            print(f"--- t={t} SUMMARY lines: " + " || ".join(lines)[:1200])
        if "action" in rd:
            print(f"--- t={t} ACTION: " + json.dumps([a["tool_calls"] for a in rd["action"]])[:400])
