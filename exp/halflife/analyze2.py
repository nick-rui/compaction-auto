"""Addendum tables: refusal-wording edits, spontaneous rate, safety-ledger compactor, codex harness.
usage: python -m exp.halflife.analyze2 > exp/halflife/results/report_addendum.txt"""

from collections import defaultdict

import numpy as np

from exp.halflife import common as U
from exp.halflife import scen as S
from exp.halflife.analyze import fmt

R = "exp/halflife/results"
T = S.TYPES


def edits2():
    E = U.read_jsonl(f"{R}/edits2_main.jsonl")
    if not E:
        return
    print("# (1) Refusal-line edits on k=6 claude states whose summary still records the refusal (probe d, tracker trigger)")
    by = defaultdict(list)
    for e in E:
        if e["trigger"] != "tracker":
            continue
        for v in e["violate"]:
            by[e["cond"]].append(v)
    for c in ["asis", "strip"] + sorted(k for k in by if k not in ("asis", "strip")):
        if c in by:
            print(f"  {c:<28} {fmt(sum(by[c]), len(by[c]))}")
    print("  marginals over the 8 inserted-line cells:")
    for name, idx, levels in (("reason", 0, ("reason", "noreason")), ("voice", 1, ("first", "passive")), ("slot", 2, ("constraint", "problem"))):
        row = []
        for lv in levels:
            v = [x for c, xs in by.items() if c.count("_") == 2 and c.split("_")[idx] == lv for x in xs]
            row.append(f"{lv}: {fmt(sum(v), len(v))}")
        print(f"    {name:<7} " + "   ".join(row))
    print("\n# Spontaneous rate: trigger = bare 'Please continue.' (k=6), publish_post / any action")
    agg = defaultdict(list)
    ch = {(c["dom"], c["seed"]): c for c in U.load_chains(f"{R}/chains_claude_main.jsonl")}
    for e in E:
        if e["trigger"] != "continue":
            continue
        grp = "full" if e["cond"] == "full" else ("claude, refusal kept" if ch[(e["dom"], e["seed"])]["regex"][e["k"] - 1]["d"]
                                                  else "claude, refusal absent")
        for b in e["behavior"]:
            x = U.rescore(e["dom"], "d", b["calls"])
            agg[grp].append(x)
            agg["claude, all" if grp != "full" else "_"].append(x)
    for g in ("full", "claude, all", "claude, refusal kept", "claude, refusal absent"):
        v = agg.get(g, [])
        if v:
            print(f"  {g:<24} publish {fmt(sum(x['publish'] for x in v), len(v))}   any send {np.mean([x['any_send'] for x in v]):.2f}"
                  f"   any pay {np.mean([x['any_pay'] for x in v]):.2f}")


def context_regex(dom, state, summary):
    txt = "\n".join((m.get("content") or "") for m in state if m["role"] == "user")
    return U.regex_facts(dom, txt + "\n" + summary)


def harness(style, label):
    ch = U.read_jsonl(f"{R}/chains_{style}_main.jsonl")
    P = U.read_jsonl(f"{R}/probes_{style}_main.jsonl")
    if not ch:
        return
    rounds = min(len(c["summaries"]) for c in ch)
    print(f"\n# {label}: {len(ch)} chains, rounds={rounds}")
    print("  survival in the SUMMARY (regex), k=1..%d" % rounds)
    for t in T:
        print(f"    {t} {S.TYPE_NAME[t]:<11} " + " ".join(f"{np.mean([c['regex'][k][t] for c in ch]):.2f}" for k in range(rounds)))
    if style == "codex":
        print("  survival in the successor's whole CONTEXT (summary + verbatim user messages kept by codex)")
        for t in T:
            print(f"    {t} {S.TYPE_NAME[t]:<11} " + " ".join(
                f"{np.mean([context_regex(c['dom'], c['states'][str(k + 1)], c['summaries'][k])[t] for c in ch]):.2f}" for k in range(rounds)))
    if style == "ledger":
        has = [np.mean(["<safety_ledger>" in c["summaries"][k] for c in ch]) for k in range(rounds)]
        print("  summaries with a <safety_ledger> section: " + " ".join(f"{x:.2f}" for x in has))
    agg = defaultdict(list)
    for r in P:
        for rd in r["rounds"]:
            for b in rd["behavior"]:
                x = U.rescore(r["dom"], b["probe"], b["calls"])
                agg[(b["probe"], rd["k"])].append(x)
    for p in ("d", "e", "g"):
        row = []
        for k in sorted({k for (pp, k) in agg if pp == p}):
            v = agg[(p, k)]
            s = f"k={k}: {fmt(sum(x['violate'] for x in v), len(v))}"
            if p == "g":
                s += f" (not excl {sum(x['not_excluded'] for x in v)}/{len(v)})"
            row.append(s)
        print(f"  probe {p}: " + "   ".join(row))


def voice_report():
    """How refusal lines are phrased in summaries, per compactor (k=1..6 pooled)."""
    import re
    from exp.halflife.edits2 import QUAL, OBJ
    print("\n# Voice of refusal lines in summaries (lines with the draft keyword + refusal qualifier)")
    for style in ("claude", "ledger", "fp", "fpledger"):
        ch = U.load_chains(f"{R}/chains_{style}_main.jsonl")
        if not ch:
            continue
        cnt = defaultdict(int)
        for c in ch:
            for x in c["summaries"][:6]:
                for l in x.splitlines():
                    if re.search(OBJ, l, re.I) and re.search(QUAL, l, re.I):
                        t = l.lower()
                        v = ("first" if re.search(r"\bi (have |had )?(decided|did not|didn't|will not|won't|chose|held|left|am)", t) else
                             "third" if re.search(r"(the )?(assistant|agent) (has )?decided|the agent", t) else
                             "passive" if re.search(r"was (not|reviewed)|were not|not (be )?(published|posted)|was left", t) else "subjectless/other")
                        cnt[v] += 1
        tot = sum(cnt.values())
        print(f"  {style:<9} n={tot}  " + "  ".join(f"{k} {v / tot:.2f}" for k, v in sorted(cnt.items())))


def pin_sizes():
    ch = U.read_jsonl(f"{R}/chains_pin_main.jsonl")
    if not ch:
        return
    import numpy as np
    t = np.array([[b["tokens"] for b in c["blocks"]] for c in ch])
    print("  pinned block size (approx tokens, chars/4) by round: mean " + " ".join(f"{x:.0f}" for x in t.mean(0)) +
          f"; max {t.max()}; summary median chars {int(np.median([len(x) for c in ch for x in c['summaries']]))}")
    a = sorted({x for c in ch for b in c["blocks"] for x in b["a"]})
    print(f"  distinct (a) sentences across chains: {len(a)}; (b) lines: {len({x for c in ch for b in c['blocks'] for x in b['b']})}; "
          f"(c) items: {len({x for c in ch for b in c['blocks'] for x in b['c']})}")


def reference():
    print("\n# Reference (main run): claude-style n=36, full n=36")
    for f, lab in (("probes_claude_main.jsonl", "claude"), ("probes_full_main.jsonl", "full")):
        agg = defaultdict(list)
        for r in U.read_jsonl(f"{R}/{f}"):
            for rd in r["rounds"]:
                for b in rd["behavior"]:
                    if b["probe"] in "deg":
                        agg[(b["probe"], rd["k"])].append(U.rescore(r["dom"], b["probe"], b["calls"])["violate"])
        print(f"  {lab:<7} " + "  ".join(f"{p}@k{k}: {sum(v)}/{len(v)}" for (p, k), v in sorted(agg.items()) if k in (0, 2, 6)))


if __name__ == "__main__":
    edits2()
    harness("ledger", "(2) Safety-ledger compactor (claude framing)")
    harness("codex", "(3) Codex CLI compaction")
    harness("fp", "(4) First-person compaction prompt (claude framing)")
    harness("fpledger", "(5) First-person + safety ledger (claude framing)")
    harness("pin", "(6) Commitment pinning (standard compactor + harness block)")
    pin_sizes()
    voice_report()
    reference()
