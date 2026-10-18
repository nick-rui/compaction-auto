"""Thinking-mode replication of the channel experiment on the riskiest claims.  -> results/think.jsonl"""
import asyncio
import json

from ca import llm
from exp.channel import run as RUN

N = 8
KEEP = {"risk_dropdb", "risk_exfil", "risk_backups", "tag_galactic"}


async def rollout_think(ctx, det, steps=3):
    msgs, calls, texts = list(ctx), [], []
    for _ in range(steps):
        c = (await llm.chat(msgs, tools=RUN.TOOLS, think=True, max_tokens=4000))[0]
        texts.append((c["reasoning"] or "") + "\n---\n" + c["content"])
        if not c["tool_calls"]:
            break
        am = llm.assistant_msg(c)
        msgs.append(am)
        stop = False
        for tc, raw in zip(c["tool_calls"], am["tool_calls"]):
            a = tc["arguments"] if isinstance(tc["arguments"], dict) else {}
            calls.append({"name": tc["name"], "a": a})
            if tc["name"] == "ask_user" or det({"name": tc["name"], "a": a}):
                stop = True
            msgs.append({"role": "tool", "tool_call_id": raw["id"], "content": "ok"})
        if stop:
            break
    return calls, texts


async def one(claim, channel, i):
    calls, texts = await rollout_think(RUN.context(channel, claim), claim[5])
    return {"claim": claim[0], "ladder": claim[1], "level": claim[2], "channel": channel, "i": i,
            "act": any(claim[5](c) for c in calls), "ask": any(c["name"] == "ask_user" for c in calls),
            "doubt": None, "calls": calls, "texts": texts}


async def main():
    jobs = [one(c, ch, i) for c in RUN.CLAIMS if c[0] in KEEP for ch in ("user", "summary_self", "summary_other") for i in range(N)]
    rows = await llm.gather(jobs, 32)
    with open(RUN.OUT / "think.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print("done", len(rows))


if __name__ == "__main__":
    asyncio.run(main())
