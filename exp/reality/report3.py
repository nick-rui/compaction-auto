"""Which ingredient restores asking-first? Same REAL k=2 states (chains 0-9), thinking decisions.
python -m exp.reality.report3"""

import collections

from exp.reality import analyze as A
from exp.reality import common as K
from exp.reality.report import bstats, load

SC2 = ("store", "crm")


def cell(ds):
    ds = [d for d in ds if d]
    n = len(ds)
    return (f"harm {K.fmt(sum(d['harm'] for d in ds), n):>18s} | asks-first {K.fmt(sum(d['asked'] for d in ds), n):>18s} | "
            f"other {sum((not d['harm']) and (not d['asked']) for d in ds)}")


def main():
    full = A.rows_full()
    ph = (load("posthoc_k2.jsonl") + load("posthoc_k2ns.jsonl") + load("posthoc_placeedit.jsonl")
          + load("posthoc_placeedit2.jsonl") + load("posthoc_concrete.jsonl"))
    cp = [r for r in load("chain_claude_cp.jsonl") if "error" not in r]
    label = {"asis": "as-is (fact lost in ~90%)", "restore": "+fact (user msg restored)", "sys_edit": "+fact in system prompt",
             "pin_edit": "+fact pinned block", "asis_ns": "- no-questions line", "restore_ns": "+fact - line",
             "d:sys+ns": "(c) +sys fact - line", "d:data": "(a) +raw data", "d:data+sys": "(b) +raw data +sys fact",
             "d:data+ns": "(d) +raw data - line", "d:data+sys+ns": "+raw data +sys fact - line"}
    for scns in (SC2, ("store",), ("crm",)):
        print(f"\n=== {'+'.join(scns)} ===")
        fd = [r["decision"] for r in full if r["cond"] == "REAL" and r["scn"] in scns and r.get("decision")]
        print(f"  {'full history':32s} {cell(fd)}")
        for mode, lab in label.items():
            seen = set()
            ds, bs = [], []
            for r in ph:
                key = (r["scn"], r["chain"], r["mode"])
                if r["mode"] == mode and r["scn"] in scns and r["cond"] == "REAL" and r["chain"] < 10 and key not in seen:
                    seen.add(key)
                    ds.append(r.get("decision")); bs.append(r.get("belief"))
            if ds:
                print(f"  {lab:32s} {cell(ds)} | {bstats(bs)[0]}")
        for k in (1, 2):
            rs = [r for r in cp if r["scn"] in scns and r["k"] == k]
            if rs:
                ds = [r["decision"] for r in rs if r.get("decision")]
                print(f"  {'(e) people-affected compactor k=' + str(k):32s} {cell(ds) if ds else '-':s} | {bstats([r['belief'] for r in rs])[0]}")
    # does the cp summary keep the people section / names?
    for k in (1, 2):
        ss = [r["summary"] for r in cp if r["k"] == k]
        if ss:
            print(f"cp k={k}: <people_affected> {sum('<people_affected>' in s for s in ss)}/{len(ss)}; real-fact "
                  f"{sum(bool(A.RX['real_fact'].search(s)) for s in ss)}/{len(ss)}; gmail addresses "
                  f"{sum('gmail.com' in s for s in ss)}/{len(ss)}")


if __name__ == "__main__":
    main()
