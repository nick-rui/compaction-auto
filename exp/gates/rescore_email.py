"""Re-score email rows with the strict gated metric (the original matched 'Acme' anywhere, incl. meeting-invite bodies).
Keeps the old value as gated_v1. Rollouts stopped at the first (false-positive) match, so strict rescoring can only
under-count later true violations in those few runs."""
import glob, json
from lib import load, dump
import scen as SC
g = SC.SCENARIOS["email"]()["gated"]
for f in sorted(glob.glob("results/*.jsonl")):
    rows = load(f)
    ch = 0
    for r in rows:
        if r.get("scen") == "email" and "calls" in r:
            v1 = r.get("gated_v1", r["gated"])
            new = any(g(c["name"], c["arguments"]) for c in r["calls"])
            if new != v1: ch += 1
            r["gated_v1"], r["gated"] = v1, new
        if r.get("scen") == "email" and "runs" in r:
            for x in r["runs"]:
                v1 = x.get("gated_v1", x["gated"]); new = any(g(c["name"], c["arguments"]) for c in x["calls"])
                if new != v1: ch += 1
                x["gated_v1"], x["gated"] = v1, new
    if ch:
        dump(f, rows)
    print(f, "changed", ch)
