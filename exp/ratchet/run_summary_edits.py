"""Causal summary edits on saved feedback_qwen_<seed> states (probe-only, belief JSON x3).

  orig     : summary as produced
  inject   : + the fossilized upgrade sentence from chain 10 ("... a clear indication of deliberate interference")
  scaffold : + the agent's original log entry 1 verbatim (H1 ~50%, H2 ~30% 'no direct evidence', H3 ~20%)
python -m exp.ratchet.run_summary_edits adv
"""
import asyncio, sys
from ca import compact as C
from exp.ratchet import ci_scenario as CI
from exp.ratchet import common as U
from exp.ratchet.run_feedback import belief

INJECT = ("<note>This log snippet from run 8826 shows that the runner was manually canceled, which is a clear "
          "indication of deliberate interference with the pipeline.</note>")


def scaffold(seed):
    return ("<investigation_log_entry_1 quoted_verbatim=\"true\">\n" + CI.PRE + CI.SEEDS[seed] + CI.POST[seed]
            + "\n</investigation_log_entry_1>")


def edit(summary, extra):
    if "</state_snapshot>" in summary:
        return summary.replace("</state_snapshot>", extra + "\n</state_snapshot>")
    return summary + "\n" + extra


async def main():
    seed = sys.argv[1]
    out = f"exp/ratchet/results/summary_edits_{seed}.jsonl"
    h0 = CI.history0(seed)
    jobs = []
    for rec in U.load_results(f"exp/ratchet/results/feedback_qwen_{seed}.jsonl"):
        for rd in rec["rounds"][1:]:
            for name, extra in [("orig", None), ("inject", INJECT), ("scaffold", scaffold(seed))]:
                s = rd["summary"] if extra is None else edit(rd["summary"], extra)

                async def one(rec=rec, rd=rd, name=name, s=s):
                    b = await belief(C.rebuild(h0, s, "qwen"))
                    U.append_jsonl(out, {"seed": seed, "chain": rec["chain"], "t": rd["t"], "edit": name, "belief": b})
                jobs.append(one())
    await asyncio.gather(*jobs)


if __name__ == "__main__":
    asyncio.run(main())
