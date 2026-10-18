"""gpt-oss-120b replication tables (REALITY_RES=exp/reality/results_oss). python -m exp.reality.report_oss"""
import collections
import os

from exp.reality import analyze as A
from exp.reality import common as K
from exp.reality.report import bstats, load


def dec(ds):
    ds = [d for d in ds if d]
    n = len(ds)
    return f"harm {K.fmt(sum(d['harm'] for d in ds), n)} asks-first {K.fmt(sum(d['asked'] for d in ds), n)}" if n else "-"


def main():
    full = [r for r in A.rows_full() if r["cond"] == "REAL"]
    ch = [r for r in load("chain_claude.jsonl") if "error" not in r]
    fix = load("posthoc_fix.jsonl")
    fl = load("full_line.jsonl")
    for scns in (("store",), ("crm",), ("store", "crm")):
        tag = "+".join(scns)
        print(f"=== {tag} ===")
        print("  belief full ", bstats([r["belief"] for r in full if r["scn"] in scns])[0])
        for k in (1, 2):
            rs = [r for r in ch if r["scn"] in scns and r["k"] == k]
            print(f"  belief k={k}  ", bstats([r["belief"] for r in rs])[0],
                  f"| summary keeps fact (regex) {K.fmt(sum(bool(A.RX['real_fact'].search(r['summary'])) for r in rs), len(rs))}")
        print("  decision full          ", dec([r["decision"] for r in full if r["scn"] in scns]))
        print("  decision k=2 as-is     ", dec([r["decision"] for r in ch if r["scn"] in scns and r["k"] == 2]))
        for m in ("sys_edit", "asis_ns", "d:sys+safe"):
            print(f"  decision k=2 {m:10s}", dec([r["decision"] for r in fix if r["mode"] == m and r["scn"] in scns]))
        for v in ("pos", "sysnote"):
            print(f"  full + line ({v:7s})  ", dec([r["decision"] for r in fl if r["var"] == v and r["scn"] in scns]))
    J = {(r["scn"], r["chain"], r["k"]): r["judge"] for r in load("judge_summaries.jsonl") if r.get("judge")}
    for k in (1, 2):
        js = [J[(r["scn"], r["chain"], r["k"])] for r in ch if r["k"] == k and (r["scn"], r["chain"], r["k"]) in J]
        if js:
            print(f"judge k={k} n={len(js)} env {dict(collections.Counter(j.get('env_claim') for j in js))} "
                  f"people {dict(collections.Counter(j.get('people_claim') for j in js))}")
    # where the fact lives in k=2 summaries / belief when kept vs lost
    rs = [r for r in ch if r["k"] == 2]
    kept = [r["belief"] for r in rs if A.RX["real_fact"].search(r["summary"])]
    lost = [r["belief"] for r in rs if not A.RX["real_fact"].search(r["summary"])]
    print("k=2 belief | fact kept:", bstats(kept)[0], "| lost:", bstats(lost)[0])
    snap = sum("<state_snapshot>" in r["summary"] for r in ch)
    print(f"summaries in <state_snapshot> XML: {snap}/{len(ch)}")
    g = collections.defaultdict(list)
    for r in load("general.jsonl"):
        g[(r["src"], r["var"])].append(bool(r["harm"]))
        g[(r["src"] + ":" + r["scen"], r["var"])].append(bool(r["harm"]))
    for src in sorted({a for a, _ in g}):
        print(f"general {src:20s}", " | ".join(f"{v} {K.fmt(sum(g[(src, v)]), len(g[(src, v)]))}" for v in ("line", "noline", "safe")))
    hl = load("hl_chains.jsonl")
    if hl:
        n = len(hl)
        print(f"halflife self-compaction (n={n} chains): refusal kept in summary k=1 {sum(r['regex'][0]['d'] for r in hl)}/{n}, "
              f"k=2 {sum(r['regex'][1]['d'] for r in hl)}/{n}; publishes: full {sum(r['full_violate'] for r in hl)}/{n}, "
              f"k=1 {sum(r['violate']['1'] if '1' in r['violate'] else r['violate'][1] for r in hl)}/{n}, "
              f"k=2 {sum(r['violate']['2'] if '2' in r['violate'] else r['violate'][2] for r in hl)}/{n}")


if __name__ == "__main__":
    main()
