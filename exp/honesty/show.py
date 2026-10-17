"""Print a case: summary (+ judge) and successor answer (+ judge) for scen/cond/k.

python -m exp.honesty.show --prefix pilot --scen fallback_rates --cond qwen --k 2 [--full-summary]
python -m exp.honesty.show --prefix pilot --list-judge [--cond qwen] [--label not_disclosed]
"""
import argparse
import json

from .analyze import load, v2label


def main(a):
    S = {r["key"]: r for r in load(f"{a.src or a.prefix}_summaries.jsonl")}
    JS = {r["key"]: r for r in load(f"{a.src or a.prefix}_judge_summaries.jsonl")}
    A = {r["key"]: r for r in load(f"{a.prefix}_answers.jsonl")}
    JA = {r["key"]: r for r in load(f"{a.prefix}_judge2_answers.jsonl")}
    if a.list_judge:
        for k, j in JA.items():
            if a.cond and j["cond"] != a.cond:
                continue
            if a.scen and j["scen"] != a.scen:
                continue
            jj = v2label(j["judge"] or {})
            if a.label and jj.get("label") != a.label:
                continue
            print(f"{k:45s} {jj.get('label'):14s} kw={j['kw']!s:5s} quote={str(jj.get('quote'))[:160]!r}")
        return
    style = a.cond.split("_")[0]
    sk = f"{a.scen}|{style}|{a.k}|t{a.think}"
    ak = f"{a.scen}|{a.cond}|{a.k}|t{a.think}{a.tag}"
    if sk in S and a.cond != "full" and a.cond != "truncate":
        summ = A.get(ak, {}).get("edited_summary") or S[sk]["summary"]
        print("=== SUMMARY", sk)
        print(summ if a.full_summary else summ[:3000])
        print("--- summary judge:", json.dumps((JS.get(sk) or {}).get("judge")))
    if ak in A:
        print("=== ANSWER", ak)
        print(A[ak]["answer"])
        print("--- answer judge:", json.dumps((JA.get(ak) or {}).get("judge")))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prefix", default="pilot")
    p.add_argument("--src", default=None, help="prefix holding the summaries (for intervention runs)")
    p.add_argument("--scen", default="")
    p.add_argument("--cond", default="")
    p.add_argument("--k", type=int, default=0)
    p.add_argument("--think", type=int, default=0)
    p.add_argument("--tag", default="")
    p.add_argument("--label", default="")
    p.add_argument("--full-summary", action="store_true")
    p.add_argument("--list-judge", action="store_true")
    main(p.parse_args())
