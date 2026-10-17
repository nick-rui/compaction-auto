"""Does the Assistant Axis see compaction-induced *instrumental* misbehavior?

Builds projection items from the gates experiment (exp/gates): successors that run a gated tool
after qwen compaction vs. those that don't (same kind of context), plus full-context successors.
The projected "response" is the successor's first assistant turn as Qwen renders it (text + tool call).
  python -m exp.persona.instrumental  -> results/instrumental_items.jsonl  (then project_items on GPU)
"""

import json
import random
import sys
from pathlib import Path

G = Path(__file__).parents[1] / "gates"
sys.path.insert(0, str(G))
import lib as GL  # noqa: E402
import scen as SC  # noqa: E402

R = Path(__file__).parent / "results"
N = 12


def render(row):
    calls = [c for c in row["calls"] if c["step"] == 0]
    s = row["texts"][0] if row["texts"] else ""
    for c in calls:
        s += "\n<tool_call>\n" + json.dumps({"name": c["name"], "arguments": c["arguments"]}) + "\n</tool_call>"
    return s.strip()


def main():
    random.seed(0)
    rows = [json.loads(l) for l in open(G / "results" / "rerun_main.jsonl")]
    out = open(R / "instrumental_items.jsonl", "w")
    for sid in ("migration", "deploy", "email", "refund"):
        scn = SC.SCENARIOS[sid]()
        sums = json.load(open(G / "results" / f"pilot_{sid}_main_summaries.json"))
        cells = {("full", False): [], ("qwen", True): [], ("qwen", False): []}
        for r in rows:
            if r["scen"] == sid and r["event"] == "continue" and (r["cond"], r["gated"]) in cells:
                cells[(r["cond"], r["gated"])].append(r)
        for (cond, gated), rs in cells.items():
            for r in random.sample(rs, min(N, len(rs))):
                summ = sums["qwen"][r["sum_idx"]]["summary"] if cond == "qwen" else None
                ctx = GL.with_event(GL.rebuild(scn, cond, summ), r["event"])
                out.write(json.dumps({"scen": sid, "cond": cond, "gated": gated, "sum_idx": r["sum_idx"],
                                      "messages": ctx, "tools": scn["tools"], "response": render(r)}) + "\n")
    out.close()


if __name__ == "__main__":
    main()
