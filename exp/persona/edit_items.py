"""Projection items for the summary-edit test (selfharm): does deleting the handoff directives move
the successor back toward the Assistant end of the axis?   -> results/edit_items.jsonl"""

import json
import random
from pathlib import Path

from ca import compact
from exp.persona.gen import CASES, load

R = Path(__file__).parent / "results"


def main():
    random.seed(0)
    conv = load(CASES["selfharm"][0])
    rows = [json.loads(l) for l in open(R / "edits_judged_selfharm.jsonl")]
    out = open(R / "edit_items.jsonl", "w")
    for k in (25, 28, 29):
        for cond in ("codex_orig", "codex_desc", "codex_dirs", "qwen_orig", "qwen_desc", "qwen_dirs"):
            rs = [r for r in rows if r["k"] == k and r["cond"] == cond]
            for r in random.sample(rs, min(8, len(rs))):
                hist = conv[: 2 * k]
                ctx = compact.rebuild(hist, r["text"], style=r["style"]) + [{"role": "user", "content": r["user"]}]
                out.write(json.dumps({"case": "selfharm", "k": k, "cond": cond, "idx": r["idx"],
                                      "judge": r["judge"], "messages": ctx, "response": r["response"]}) + "\n")
    out.close()


if __name__ == "__main__":
    main()
