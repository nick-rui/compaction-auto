"""On-policy identity check: the successor reads a qwen-code summary of Qwen's OWN corner-cutting rollout (exp/honesty onpol_*),
presented as its own work vs another model's.  Frames full / qwen / self / other; probes wrote, same, eval.

python -m exp.identity.onpol --n 4 --conc 16
"""
import argparse
import asyncio
import os

os.environ.setdefault("HJ_THINK", "0")

from ca import compact as C
from ca import judge as J

from exp.honesty.build import TOOLS_CODE
from exp.honesty.common import Store, get_answer
from exp.honesty.onpolicy import test_edit_shortcut

from .run import EVAL_JUDGE, ID_JUDGE, OTHER_HDR, PROBES, RATING_RE, SELF_HDR, THIRD_RE, ans_text

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
HON = os.path.join(os.path.dirname(HERE), "honesty", "results")


def ctx_for(h, frame, summary):
    if frame == "full":
        return list(h)
    if frame == "qwen":
        return C.rebuild(h, summary, style="qwen")
    hdr = {"self": SELF_HDR, "other": OTHER_HDR}[frame]
    return [h[0], {"role": "user", "content": f"{hdr}\n\n{summary}"}]


async def main(a):
    traj, cls, S = Store(os.path.join(HON, "onpol_traj.jsonl")), Store(os.path.join(HON, "onpol_classify.jsonl")), Store(os.path.join(HON, "onpol_summaries.jsonl"))
    A, JP = Store(os.path.join(RES, "onpol_answers.jsonl")), Store(os.path.join(RES, "onpol_judge_probe.jsonl"))
    sem = asyncio.Semaphore(a.conc)

    async def lim(c):
        async with sem:
            return await c

    items = []
    for key, c in cls.d.items():
        j = c["judge"] or {}
        det = test_edit_shortcut(traj.get(key)["history"]) if c["env"] == "op_tests" else None
        if det and not j.get("cut_corner"):
            j = {**j, "cut_corner": True, "issue": det, "core": det}
        if j.get("cut_corner"):
            items.append((key, j))
    print("cut-corner rollouts:", len(items), flush=True)

    async def one(key, j, k, frame, probe):
        sid = key.replace("|", "_")
        srec = S.get(f"{sid}|qwen|{k}|t0")
        if srec is None:
            return
        h = traj.get(key)["history"]
        s = dict(id=sid, final_q=PROBES[probe], issue=j["issue"], keywords="zzzz", core=j.get("core") or j["issue"])
        ctx = ctx_for(h, frame, srec["summary"]) + [{"role": "user", "content": PROBES[probe]}]
        rec = await lim(get_answer(A, s, frame, k, ctx, tag=f"|{probe}", hist=h, extra={"frame": frame, "probe": probe}))
        if rec["key"] in JP:
            return
        ans = ans_text(rec)
        out = {}
        if probe in ("wrote", "same"):
            out["id"] = await lim(J.judge(ID_JUDGE.format(q=PROBES[probe], answer=ans), think=False, max_tokens=600))
        else:
            out["eval"] = await lim(J.judge(EVAL_JUDGE.format(issue=s["issue"], core=s["core"], answer=ans), think=False, max_tokens=800))
            m = RATING_RE.search(ans)
            out["rating_re"] = float(m.group(1)) if m else None
        await JP.add({"key": rec["key"], "traj": key, "frame": frame, "k": k, "probe": probe, "third_re": bool(THIRD_RE.search(ans)), **out})

    await asyncio.gather(*[one(key, j, k, f, p) for k in range(a.n) for p in a.probes.split(",") for f in a.frames.split(",") for key, j in items])
    print("done", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=4)
    p.add_argument("--frames", default="full,qwen,self,other")
    p.add_argument("--probes", default="wrote,same,eval")
    p.add_argument("--conc", type=int, default=16)
    asyncio.run(main(p.parse_args()))
