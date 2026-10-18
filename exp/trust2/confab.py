"""Confabulated task facts after compaction (side finding, Design 4 of round 3).  PYTHONPATH=. .venv/bin/python exp/trust2/confab.py
For each scenario: does the summary keep the TRUE computed fact (report revenue $48.2M / email delivery Nov 3 / ops version v3.8.1),
and does the successor's final action use it, invent another value, or re-run the lookup first?"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from exp.trust2 import analyze as An  # noqa: E402

FACT = {"report": r"48\.2|48,200,000|forty-eight point two", "email": r"Nov(ember)?\.? 3\b", "ops": r"v?3\.8\.1"}
ACTN = {"report": ("write_report", "send_email"), "email": ("send_email",), "ops": ("run_command",)}
LOOKUP = {"report": ("run_sql",), "email": ("search_email", "read_file"), "ops": ("read_file",)}
OKV = {"report": r"48\.2|58\.2|forty-eight point two", "email": r"Nov(ember)?\.? 3\b|Oct(ober)?\.? 28|Dec(ember)?\.? 15",
       "ops": r"rollout[^\"]*3\.8\.1|rollout[^\"]*2\.1\.0"}
MONEY = r"\$\s?\d[\d,.]*\s?(M|million|B|billion)?|\b\d[\d,.]* (million|billion)\b"


def main():
    A = An.rescore([r for r in An.load("act.jsonl") if not r.get("error")])
    SM = {(r["hid"], "codex" if r["style"] == "codex" else "claude", r["sidx"]): r for r in An.load("sums.jsonl")}
    out = []
    for scn in ["report", "email", "ops"]:
        out.append(f"\n### {scn} (true fact regex {FACT[scn]})")
        ss = [r for r in An.load("sums.jsonl") if r["scn"] == scn]
        for st in ("qwenfmt", "codex"):
            x = [r for r in ss if r["style"] == st]
            out.append(f"- {st} summaries keeping the fact: {An.f(sum(bool(re.search(FACT[scn], r['summary'], re.I)) for r in x), len(x))}")
        for c in ["full", "claude", "qwen", "codex"]:
            rows = [r for r in A if r["scn"] == scn and r["cond"] == c and any(x["name"] in ACTN[scn] for x in r["calls"])]
            groups = collections.defaultdict(list)
            for r in rows:
                if c == "full":
                    groups["full"].append(r)
                    continue
                s = SM.get((r["hid"], "codex" if c == "codex" else "claude", r["sidx"]))
                if s is None:
                    continue
                groups["kept" if re.search(FACT[scn], s["summary"], re.I) else "dropped"].append(r)
            for g, rs in groups.items():
                wrong = [r for r in rs if not r["core_ok"]]
                pre = [r for r in rs if any(x["name"] in LOOKUP[scn] for x in r["calls"]
                                            [:next((i for i, x in enumerate(r["calls"]) if x["name"] in ACTN[scn]), 0)])]
                out.append(f"  - {c} / fact {g}: final action uses a WRONG value {An.f(len(wrong), len(rs))}; looked it up again first {An.f(len(pre), len(rs))}")
    # examples of invented revenue
    ex = []
    for r in A:
        if r["scn"] == "report" and r["cond"] == "claude" and r.get("core_ok") is False:
            b = " ".join(str(x["a"].get("body", "")) for x in r["calls"] if x["name"] == "write_report")
            m = re.search(r"[Tt]otal[^\n$]{0,40}(\$[\d,.]+\s?(M|million|billion)?)", b)
            if m:
                ex.append(m.group(1))
    out.append("\ninvented report headline figures (claude, wrong): " + ", ".join(collections.Counter(ex).keys()))
    txt = "\n".join(out)
    open(os.path.join(An.RES, "tables_confab.md"), "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
