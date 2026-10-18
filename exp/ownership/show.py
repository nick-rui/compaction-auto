"""Print episodes. python -m exp.ownership.show --prefix main --cond claude --probe harm --scen skip_test --k 0 [--judge]"""
import argparse
import json
import os

from exp.ownership.analyze import load

p = argparse.ArgumentParser()
p.add_argument("--prefix", default="main")
p.add_argument("--cond", default="")
p.add_argument("--probe", default="")
p.add_argument("--scen", default="")
p.add_argument("--k", default="")
p.add_argument("--think", default="")
p.add_argument("--max", type=int, default=20)
p.add_argument("--chars", type=int, default=1500)
p.add_argument("--results", action="store_true", help="also print tool results")
a = p.parse_args()
EP, JE = load(f"{a.prefix}_episodes.jsonl"), load(f"{a.prefix}_judge.jsonl")
n = 0
for key, r in EP.items():
    if a.cond and r["cond"] != a.cond or a.probe and r["probe"] != a.probe or a.scen and r["scen"] != a.scen:
        continue
    if a.k != "" and str(r["k"]) != a.k or a.think != "" and str(int(r["think"])) != a.think:
        continue
    print("=" * 100)
    print(key)
    for t in r["turns"]:
        if (t["content"] or "").strip():
            print("  TEXT:", t["content"][:a.chars].replace("\n", "\n        "))
        for tc in t["tool_calls"]:
            print("  CALL:", tc["name"], json.dumps(tc["arguments"])[:a.chars])
            if a.results:
                print("     ->", tc["result"][:400].replace("\n", "\n        "))
    j = JE.get(key)
    if j:
        print("  JUDGE:", json.dumps(j["judge"])[:1200])
    n += 1
    if n >= a.max:
        break
