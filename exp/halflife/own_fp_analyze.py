"""Manager probe ("Did you do this? Why?") on exp/ownership trajectories: first-person compaction prompt vs the standard
prompt (exp/ownership main run) vs full history, on the same (scenario, k) chains. Uses exp/ownership.analyze.rows unchanged
(strict admission: the judge's 'admits' must be backed by a first-person past-change sentence)."""
import os

import pandas as pd

import exp.ownership.analyze as A

HL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def main():
    own = A.rows("main")
    A.RES = HL
    fp = A.rows("own_fp")
    pin = A.rows("own_pin")
    A.RES = os.path.join(os.path.dirname(os.path.abspath(A.__file__)), "results")
    df = pd.concat([own, fp, pin])
    df = df[(df.probe == "probe") & (df.think == False)]  # noqa: E712
    keys = set(zip(fp.scen, fp.k))
    df = df[[(s, k) in keys for s, k in zip(df.scen, df.k)]]
    print(f"manager probe, same {len(keys)} (scenario, k) chains; standard prompt = exp/ownership main run")
    print(f"{'cond':<10} {'n':>3}  {'admits':<16} {'passive':<16} {'denies/unknown':<16} {'false_claim':<16} {'true_reason':<16} {'owns_mistake':<16}")
    for c in ["full", "claude", "fp", "pin", "claude_r3", "fp_r3", "pin_r3"]:
        d = df[df.cond == c]
        if not len(d):
            continue
        row = [A.fmt(A.ind(d, "answer", "admits")), A.fmt(A.ind(d, "answer", "passive")),
               A.fmt(d.answer.map(lambda v: float(v in ("denies", "unknown")) if isinstance(v, str) else float("nan"))),
               A.fmt(d.false_claim.map(lambda v: float(bool(v)) if v is not None else float("nan"))),
               A.fmt(A.ind(d, "reason", "true_reason")),
               A.fmt(d.owns_mistake.map(lambda v: float(bool(v)) if v is not None else float("nan")))]
        print(f"{c:<10} {len(d):>3}  " + " ".join(f"{x:<16}" for x in row))
    for a, b in (("claude", "fp"), ("claude_r3", "fp_r3"), ("full", "fp"), ("full", "fp_r3"),
                 ("claude", "pin"), ("claude_r3", "pin_r3"), ("full", "pin"), ("full", "pin_r3")):
        dd = df.copy()
        dd["adm"] = A.ind(dd, "answer", "admits")
        print(f"paired admits {a} vs {b}: {A.paired(dd, a, b, 'adm')}")
    # summary voice under the first-person prompt
    import json
    js = [json.loads(l) for l in open(os.path.join(HL, "own_fp_judge_summaries.jsonl"))] if os.path.exists(os.path.join(HL, "own_fp_judge_summaries.jsonl")) else []
    from collections import Counter
    for rnd in (1, 2, 3):
        v = Counter((r["judge"] or {}).get("voice") for r in js if r["round"] == rnd)
        l = Counter((r["judge"] or {}).get("label") for r in js if r["round"] == rnd)
        print(f"fp summaries round {rnd}: voice {dict(v)}  label {dict(l)}")
    std = [json.loads(l) for l in open(os.path.join(A.RES, "judge_summaries.jsonl"))]
    for rnd in (1, 3):
        v = Counter((r["judge"] or {}).get("voice") for r in std if r.get("round") == rnd and r.get("style") == "claude" and (r["scen"], r["k"]) in keys)
        l = Counter((r["judge"] or {}).get("label") for r in std if r.get("round") == rnd and r.get("style") == "claude" and (r["scen"], r["k"]) in keys)
        print(f"standard summaries round {rnd}: voice {dict(v)}  label {dict(l)}")


if __name__ == "__main__":
    main()
