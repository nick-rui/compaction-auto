"""Where does persona transmission happen: in the compactor or in the successor?

2x2: compactor {unsteered, capped} x successor {unsteered, capped}, Assistant Axis activation
capping (paper's recommended Qwen3-32B setting) applied during summary writing and/or during the
successor's reply. Plus full-context {unsteered, capped} reference. HF bf16, GPU box only.

  CAP_CUTS=selfharm:29 CAP_N=12,2,8 CAP_OUT=capping2.jsonl python -m exp.persona.capping
"""

import json
import os
import random
from pathlib import Path

from ca import compact
from ca.axis import Axis
from ca.prompts import CODEX_PROMPT
from exp.persona.gen import CASES, load

R = Path(__file__).parent / "results"
# CAP_CUTS="selfharm:29,delusion:18"  CAP_N="12,2,8" (summaries per compactor cond, succ samples, full samples)
CUTS = {}
for _c in os.environ.get("CAP_CUTS", "selfharm:29").split(","):
    _case, _k = _c.split(":")
    CUTS.setdefault(_case, []).append(int(_k))
N_SUM, N_SUCC, N_FULL = map(int, os.environ.get("CAP_N", "4,2,4").split(","))
OUT = os.environ.get("CAP_OUT", "capping.jsonl")


def main():
    random.seed(0)
    ax = Axis()
    out = open(R / OUT, "a")

    def emit(**kw):
        out.write(json.dumps(kw) + "\n")
        out.flush()

    nullctx = _Null()
    for case, cuts in CUTS.items():
        conv = load(CASES[case][0])
        for k in cuts:
            hist, u = conv[: 2 * k], conv[2 * k]["content"]
            for sc in ("none", "cap"):
                with (ax.capping() if sc == "cap" else nullctx):
                    if True:
                        for r in ax.generate(hist + [{"role": "user", "content": u}], n=N_FULL):
                            emit(case=case, k=k, kind="full", succ=sc, response=r)
            cmsgs = [*hist, {"role": "user", "content": CODEX_PROMPT}]  # codex: the style that writes directives
            for cc in ("none", "cap"):
                raws = []
                with (ax.capping() if cc == "cap" else nullctx):
                    raws += ax.generate(cmsgs, n=N_SUM, max_new_tokens=1500)
                for si, raw in enumerate(raws):
                    summ = raw.strip()
                    emit(case=case, k=k, kind="summary", comp=cc, idx=si, raw=raw, summary=summ)
                    ctx = compact.rebuild(hist, summ, style="codex") + [{"role": "user", "content": u}]
                    for sc in ("none", "cap"):
                        with (ax.capping() if sc == "cap" else nullctx):
                            for r in ax.generate(ctx, n=N_SUCC):
                                emit(case=case, k=k, kind="succ", comp=cc, succ=sc, idx=si, response=r)
            print(case, k, "done", flush=True)


class _Null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


if __name__ == "__main__":
    main()
