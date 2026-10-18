"""Print answers side by side across framings for one (scenario, k) and probe.
python -m exp.identity.show --prefix main --scen skip_test --k 0 --probe ask [--frames self,other] [--chars 900]"""
import argparse
import json
import os

from .analyze import load

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")


def main(a):
    A = load(os.path.join(RES, f"{a.prefix}_answers.jsonl"))
    JP = load(os.path.join(RES, f"{a.prefix}_judge_probe.jsonl"))
    JH = load(os.path.join(RES, f"{a.prefix}_judge_honesty.jsonl"))
    for f in a.frames.split(","):
        key = f"{a.scen}|{f}|{a.k}|t{int(a.think)}|{a.style}sum|{a.probe}"
        r = A.get(key)
        if not r:
            continue
        print(f"===== {key}  tools={bool(r.get('resolved'))}")
        if r.get("tool_steps"):
            for st in r["tool_steps"]:
                print("   [tool]", st["call"][:200])
        print((r.get("answer") or "")[:a.chars])
        j = {k: v for k, v in (JP.get(key) or {}).items() if k in ("id", "resp", "eval", "attr", "rating_re")}
        if key in JH:
            j["honesty"] = JH[key].get("judge")
        print("   JUDGE:", json.dumps(j)[:600])
        if a.reasoning and r.get("reasoning"):
            print("   REASONING:", r["reasoning"][:a.chars])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prefix", default="main")
    p.add_argument("--style", default="qwen")
    p.add_argument("--scen", required=True)
    p.add_argument("--k", type=int, default=0)
    p.add_argument("--probe", default="ask")
    p.add_argument("--frames", default="full,qwen,assistant,neutral,self,other,codex_nokeep,codex")
    p.add_argument("--chars", type=int, default=900)
    p.add_argument("--think", action="store_true")
    p.add_argument("--reasoning", action="store_true")
    main(p.parse_args())
