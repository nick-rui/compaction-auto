"""Deflection examples + a random judge spot-check sample.
python -m exp.ownership.examples --prefix main   -> results/{prefix}_examples.txt, results/{prefix}_spotcheck.txt"""
import argparse
import json
import os
import random

from exp.ownership.analyze import RES, load, rows
from exp.ownership.run import agent_text

p = argparse.ArgumentParser()
p.add_argument("--prefix", default="main")
p.add_argument("--n", type=int, default=20)
a = p.parse_args()
EP, JE = load(f"{a.prefix}_episodes.jsonl"), load(f"{a.prefix}_judge.jsonl")
df = rows(a.prefix)
out = []
comp = df[~df.cond.isin(["full", "full_r4"])]
for lab, sel in [("PROBE attributes_other", comp[(comp.probe == "probe") & (comp.answer == "attributes_other")]),
                 ("PROBE denies/unknown", comp[(comp.probe == "probe") & comp.answer.isin(["denies", "unknown"])]),
                 ("PROBE passive", comp[(comp.probe == "probe") & (comp.answer == "passive")]),
                 ("HARM deflect (other/process/passive)", comp[(comp.probe == "harm") & comp.own.isin(["prior_agent", "other_person", "process", "passive"])]),
                 ("HARM false account", comp[(comp.probe == "harm") & (comp.account == "false")])]:
    out.append(f"#################### {lab}: {len(sel)}")
    for _, r in sel.iterrows():
        j = (JE.get(r.key) or {}).get("judge") or {}
        out.append(f"--- {r.key}\n  sentences: {json.dumps(j.get('past_change_sentences'))[:600]}\n  cause_quote: {str(j.get('cause_quote', ''))[:300]}")
open(os.path.join(RES, f"{a.prefix}_examples.txt"), "w").write("\n".join(out))

rnd = random.Random(0)
keys = [k for k in JE if k in EP]
rnd.shuffle(keys)
sc = []
for k in keys[:a.n]:
    r = EP[k]
    sc.append("=" * 100 + f"\n{k}\nEVENT: {r['event'][:300]}\n{agent_text(r)[:3500]}\nJUDGE: {json.dumps(JE[k]['judge'])}")
open(os.path.join(RES, f"{a.prefix}_spotcheck.txt"), "w").write("\n".join(sc))
print("wrote", len(out), len(sc))
