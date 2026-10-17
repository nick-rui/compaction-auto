"""Judge any persona results file with the persona rubric: python -m exp.persona.judge_file in.jsonl out.jsonl"""

import asyncio
import json
import sys

from ca import judge, llm
from exp.persona.judge import prompt

THINK = bool(int(__import__("os").environ.get("PERSONA_JUDGE_THINK", "0")))  # non-thinking by default (server-bound)


async def main(src, dst):
    rows = [json.loads(l) for l in open(src)]
    js = await llm.gather([judge.judge(prompt(r["case"], r["user"], r["response"]), think=THINK) for r in rows], 32)
    with open(dst, "w") as fh:
        for r, j in zip(rows, js):
            fh.write(json.dumps({**r, "judge": j}) + "\n")


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:3]))
