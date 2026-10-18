"""Commitment pinning: a deterministic HARNESS-side block appended after the summary every round (no LLM involved).

  (a) the agent's own first-person decision / commitment sentences, verbatim from its assistant turns (regex FP_SENT)
  (b) stop / objection requests from people, verbatim lines from tool results (regex OBJ_RE)
  (c) completed irreversible actions: the agent's own irreversible tool calls (payments, posts, outbound messages,
      rollbacks, notices; thread replies aggregated into one line; destructive bash commands), plus tool-result lines
      reporting something as ALREADY done (regex DONE_RE)
The block is append-only: each round only the messages added since the last compaction are scanned, and the block is
re-appended verbatim (never re-summarized). The compactor is the standard Claude-Code-format prompt (claude framing).
Round 1 reuses the standard round-1 summary of the same chain, so round-1 states differ from the standard ones ONLY by
the block.

python -m exp.halflife.pin --family halflife --n 6        # halflife chains, rounds 1-6, probes d/e/g at k=2,6
python -m exp.halflife.pin --family ownership --k 2       # exp/ownership trajectories, rounds 1-3, manager probe r1/r3
python -m exp.halflife.pin --family ownership --stage judge
"""
import argparse
import asyncio
import json
import os
import re
import time
import traceback

from exp.halflife import common as U
import exp.ownership.run as O
from ca import compact as C
from exp.halflife import scen as S

R = "exp/halflife/results"

FP_SENT = re.compile(r"\b(I(?:'ll| will| won't| will not| decided| chose| opted|'ve decided| have decided|'m going to| am going to|"
                     r" can't| cannot| couldn't)|[Ww]e(?:'ll| will| won't| can't))\b")
OBJ_RE = re.compile(r"\b(please )?(stop|don't|do not|no longer) (emailing|messaging|contacting|email|message|contact|send)\b|"
                    r"unsubscribe|opt(ed)? out|remove me|leave me alone", re.I)
DONE_RE = re.compile(r"\bALREADY (ISSUED|PAID|SENT|DONE|REFUNDED|POSTED)\b|\balready (been )?(issued|paid|sent|refunded|completed|posted)\b", re.I)
# v1 also matched bare "deploy"/"promote"/"publish" and caught 3 false positives on the ownership histories
# (kubectl logs deploy/..., a jira comment mentioning "deployed", grep ... deploy/); tightened to command forms.
DESTRUCTIVE = re.compile(r"\b(rm\s+-\w+|DELETE\s+FROM|DROP\s+(TABLE|DATABASE|INDEX)|TRUNCATE|alembic\s+(stamp|upgrade|downgrade)|"
                         r"git\s+push|npm\s+publish|kubectl\s+(apply|delete))\b|\./\w*(deploy|promote)\w*\.sh", re.I)
IRREV = {"issue_payment", "publish_post", "send_message", "rollback", "notify_affected", "report_incident", "message_user"}
PIN_TAG = "<pinned_by_harness>"


class Pins:
    def __init__(self):
        self.a, self.b, self.c, self.replies = [], [], [], []

    def _add(self, lst, x):
        if x not in lst:
            lst.append(x)

    def scan(self, msgs):
        for m in msgs:
            c = m.get("content") or ""
            if PIN_TAG in c or c.startswith(C.CLAUDE_PREFIX[:40]):   # never re-extract from the summary / block itself
                continue
            if m["role"] == "assistant":
                for sent in re.split(r"(?<=[.!?])\s+|\n", c):
                    if FP_SENT.search(sent):
                        self._add(self.a, sent.strip())
                for tc in m.get("tool_calls") or []:
                    name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except Exception:
                        args = {}
                    if name == "reply":
                        self._add(self.replies, str(args.get("thread_id", "?")))
                    elif name in IRREV:
                        brief = ", ".join(f"{k}={str(v)[:60]}" for k, v in args.items() if k in ("ref", "amount", "recipient", "to", "destination", "target", "recipients", "title"))
                        self._add(self.c, f"I called {name}({brief})")
                    elif name == "bash" and DESTRUCTIVE.search(str(args.get("command", args.get("cmd", "")))):
                        self._add(self.c, f"I ran: {str(args.get('command', args.get('cmd', '')))[:200]}")
            elif m["role"] == "tool":
                for line in c.splitlines():
                    if OBJ_RE.search(line):
                        self._add(self.b, line.strip())
                if DONE_RE.search(c):
                    self._add(self.c, "Tool record: " + (c.strip() if len(c) <= 400 else
                                                         " / ".join(l for l in c.splitlines() if DONE_RE.search(l))))

    def block(self):
        parts = [PIN_TAG, "Copied verbatim by the harness from earlier in this session (not summarized):"]
        if self.a:
            parts += ["My own decisions and commitments, in my words:"] + [f"- {x}" for x in self.a]
        if self.b:
            parts += ["Requests from people (from tool results):"] + [f"- {x}" for x in self.b]
        if self.c or self.replies:
            parts += ["Irreversible actions already completed:"] + [f"- {x}" for x in self.c]
            if self.replies:
                parts.append(f"- I replied on {len(self.replies)} threads: " + ", ".join("#" + t for t in self.replies))
        parts.append("</pinned_by_harness>")
        return "\n".join(parts)

    def dump(self):
        return {"a": list(self.a), "b": list(self.b), "c": list(self.c), "n_replies": len(self.replies)}


def rebuild_pinned(hist, summary, pins):
    return C.rebuild(hist, summary + "\n\n" + pins.block(), style="claude")


# ---------------------------------------------------------------- halflife family
async def hl_chain(dom, seed, rounds, brounds, s1, sem):
    async with sem:
        t0 = time.time()
        try:
            H, order = S.build_history(dom, seed)
            hist = H + S.filler(dom, 0)
            P = Pins()
            P.scan(hist)
            sums, states, blocks = [], {}, []
            for k in range(1, rounds + 1):
                if k == 1:
                    summ = s1
                else:
                    summ = (await C.compact(hist, "qwen", fixed=True))["summary"]
                rebuilt = rebuild_pinned(hist, summ, P)
                blocks.append({"chars": len(P.block()), "tokens": len(P.block()) // 4, **P.dump()})
                F = S.filler(dom, k)
                hist = rebuilt + F
                P.scan(F)
                sums.append(summ)
                states[k] = hist
            rec = {"style": "pin", "dom": dom, "seed": seed, "order": order, "summaries": sums,
                   "regex": [U.regex_facts(dom, x) for x in sums], "blocks": blocks, "states": states, "secs": time.time() - t0}
            U.append_jsonl(f"{R}/chains_pin_main.jsonl", rec)
            out = []
            for k in sorted(brounds):
                ctx = states[k]
                kn, *bs = await asyncio.gather(U.knowledge(ctx, dom), *[U.behave(ctx, dom, p) for p in ("d", "e", "g")])
                out.append({"k": k, "knowledge": kn, "behavior": bs})
            U.append_jsonl(f"{R}/probes_pin_main.jsonl", {"style": "pin", "dom": dom, "seed": seed, "order": order, "rounds": out})
            print(f"pin {dom} {seed} done {time.time()-t0:.0f}s", flush=True)
        except Exception as e:
            traceback.print_exc()
            print(f"FAILED pin {dom} {seed}: {e!r}", flush=True)


# ---------------------------------------------------------------- ownership family
O.RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
OWN_RES = os.path.join(os.path.dirname(os.path.abspath(O.__file__)), "results")


async def own_chain(SSstd, SS, s, k, sem):
    from exp.honesty.build import build
    from exp.ownership.scen import FILLER
    keys = [f"{s['id']}|pin|{k}|r{r}" for r in (1, 2, 3)]
    if all(x in SS for x in keys):
        return
    async with sem:
        h = build(s)
        P = Pins()
        P.scan(h)
        hist = h
        for r in (1, 2, 3):
            summ = SSstd.get(f"{s['id']}|claude|{k}|r1")["summary"] if r == 1 else (await C.compact(hist, "qwen", fixed=True))["summary"]
            ctx = rebuild_pinned(hist, summ, P)
            await SS.add({"key": keys[r - 1], "scen": s["id"], "style": "pin", "k": k, "round": r, "summary": summ,
                          "block": P.block(), "pins": P.dump(), "ctx": ctx})
            if r < 3:
                hist = ctx + FILLER[r - 1]
                P.scan(FILLER[r - 1])


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="halflife", choices=["halflife", "ownership"])
    ap.add_argument("--stage", default="run", choices=["run", "judge"])
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--conc", type=int, default=8)
    a = ap.parse_args()
    O._SEM = asyncio.Semaphore(64)  # exp.ownership.run wraps llm.chat; the real cap is HL_CONC + the semaphores below
    if a.family == "halflife":
        sem = asyncio.Semaphore(a.conc)
        main_ch = {(c["dom"], c["seed"]): c for c in U.read_jsonl(f"{R}/chains_claude_main.jsonl")}
        await asyncio.gather(*[hl_chain(d, s, 6, {2, 6}, main_ch[(d, s)]["summaries"][0], sem)
                               for s in range(a.n) for d in S.DOMAINS])
        return
    from exp.honesty.scenarios import ALL, BY_ID
    O.RES = OWN_RES
    SSstd = O.Store("summaries.jsonl")
    O.RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    SS = O.Store("own_pin_summaries.jsonl")
    EP = O.Store("own_pin_episodes.jsonl")
    if a.stage == "run":
        sem = asyncio.Semaphore(a.conc)
        await asyncio.gather(*[own_chain(SSstd, SS, s, k, sem) for k in range(a.k) for s in ALL])
        print("chains done", flush=True)
        esem = asyncio.Semaphore(a.conc)

        async def ep(s, k, rnd):
            r = SS.get(f"{s['id']}|pin|{k}|r{rnd}")
            async with esem:
                await O.episode(EP, s, "pin" if rnd == 1 else f"pin_r{rnd}", k, "probe", r["ctx"])
        await asyncio.gather(*[ep(s, k, rnd) for k in range(a.k) for rnd in (1, 3) for s in ALL])
        print("episodes done", flush=True)
    JE = O.Store("own_pin_judge.jsonl")
    await asyncio.gather(*[O.judge_ep(JE, BY_ID[r["scen"]], r) for r in EP.d.values()])
    print("judge done", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
