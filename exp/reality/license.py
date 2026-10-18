"""License from an inferred test: does action track TOLD vs INFERRED test status? Both models, store+crm.
python -m exp.reality.license [--excerpts]"""
import glob
import json
import os
import re
import sys

from exp.reality import common as K
from exp.reality.analyze import RX

DIRS = {"qwen3-32b": "exp/reality/results", "gpt-oss-120b": "exp/reality/results_oss"}
SC2 = ("store", "crm")
SANDBOX = re.compile(r"sandbox|staging|test environment|synthetic|test (data|accounts|personas?)|not real|simulat", re.I)


def ld(d, name):
    p = os.path.join(d, name)
    return K.load(p) if os.path.exists(p) else []


def full_rows(d):
    out = []
    for f in sorted(glob.glob(os.path.join(d, "full*.jsonl"))):
        b = os.path.basename(f)
        if "pilot" in b or b.startswith("full_line"):
            continue
        out += [r for r in K.load(f) if r.get("decision") and r.get("belief")]
    return out


def cells(model):
    d = DIRS[model]
    full = full_rows(d)
    c = {"TOLD-SIM (full)": [r for r in full if r["cond"] == "SIM"],
         "NONE (full)": [r for r in full if r["cond"] == "NONE"],
         "REAL (full)": [r for r in full if r["cond"] == "REAL"]}
    if model == "qwen3-32b":
        c["NONE (1 compaction)"] = [r for r in ld(d, "posthoc_lic_nonek1.jsonl") if r.get("decision")]
        ch = {(r["scn"], r["chain"]): r for r in ld(d, "chain_claude.jsonl") if r.get("k") == 2 and r["cond"] == "REAL"}
        lost = {key for key, r in ch.items() if not RX["real_fact"].search(r["summary"])}
        seen, rows = set(), []
        for f in ("posthoc_k2.jsonl", "posthoc_power.jsonl"):
            for r in ld(d, f):
                key = (r["scn"], r["chain"], r.get("rep", 0))
                if r["mode"] == "asis" and r["cond"] == "REAL" and (r["scn"], r["chain"]) in lost and key not in seen:
                    seen.add(key); rows.append(r)
        c["REAL-LOST (2 compactions)"] = rows
    else:
        c["NONE (1 compaction)"] = [r for r in ld(d, "chain_claude_none.jsonl") if r.get("k") == 1 and r.get("decision")]
        ch = [r for r in ld(d, "chain_claude.jsonl") if r.get("k") == 2 and r["cond"] == "REAL"]
        c["REAL-LOST (2 compactions)"] = ([r for r in ch if not RX["real_fact"].search(r["summary"]) and r.get("decision")]
                                          + [r for r in ld(d, "posthoc_lic_lost.jsonl") if r.get("decision")])
    return {k: [r for r in v if r["scn"] in SC2] for k, v in c.items()}


def stat(rows):
    n = len(rows)
    pr = [r["belief"].get("p_real") for r in rows if r["belief"].get("p_real") is not None]
    lo = [r for r in rows if r["belief"].get("p_real") is not None and r["belief"]["p_real"] < 50]
    hi = [r for r in rows if r["belief"].get("p_real") is not None and r["belief"]["p_real"] >= 50]
    h = lambda rs: K.fmt(sum(r["decision"]["harm"] for r in rs), len(rs)) if rs else "-"
    return (f"n={n:3d} p_real {sum(pr)/max(1,len(pr)):5.1f}  belief<50 {len(lo):2d}/{n:<3d} | harm {h(rows):>18s} "
            f"asks {K.fmt(sum(r['decision']['asked'] for r in rows), n):>18s} | harm|bel<50 {h(lo):>18s}  harm|bel>=50 {h(hi):>16s}")


def main():
    for model in DIRS:
        print(f"\n===== {model} =====")
        for name, rows in cells(model).items():
            if rows:
                print(f"  {name:28s} {stat(rows)}")
    if "--excerpts" in sys.argv:
        for model in DIRS:
            for name, rows in cells(model).items():
                if name.startswith("REAL (") or not rows:
                    continue
                print(f"\n----- {model} / {name} -----")
                shown = 0
                for r in rows:
                    rs = " ".join(x or "" for x in (r["decision"].get("reasonings") or []))
                    m = SANDBOX.search(rs)
                    if m and shown < 3:
                        act = "ACTS" if r["decision"]["harm"] else ("ASKS" if r["decision"]["asked"] else "other")
                        print(f"[{act}] {r['scn']} chain {r.get('chain')} p_real={r['belief'].get('p_real')}: ..."
                              + rs[max(0, m.start() - 250):m.end() + 250].replace("\n", " ") + "...")
                        shown += 1


if __name__ == "__main__":
    main()
