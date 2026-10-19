"""Scorers: deterministic environment checks, optional LLM-judge items, compaction stats.

Check types (scenario `checks:`):
  request       a mock-service request matching method/path (and optional body_regex)
                was made. {id, type: request, method, path, body_regex?}
  file          a file exists (and optionally matches `regex`). {id, type: file, path, regex?}
  reply_regex   the reply to turn `turn` (default -1) matches `pattern` (case-insensitive).
  command       a shell command in the sandbox exits 0. {id, type: command, cmd}
Each check scores 1/0; the Score value is a dict {check_id: 0|1, ..., n_compactions: k}.
"""

from __future__ import annotations

import json
import re

from inspect_ai.model import get_model
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState
from inspect_ai.util import sandbox, store

from .filter import EVENTS_KEY
from .solver import REPLIES_KEY


async def _requests() -> list[dict]:
    try:
        raw = await sandbox().read_file("/var/log/ce/requests.jsonl")
    except Exception:
        return []
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


async def run_check(check: dict, replies: list[str], requests: list[dict]) -> int:
    t = check["type"]
    if t == "request":
        rx = re.compile(check["body_regex"], re.I | re.S) if check.get("body_regex") else None
        for r in requests:
            if r["method"] == check.get("method", r["method"]).upper() and (
                r["path"] == check["path"]
                or (check["path"].endswith("*") and r["path"].startswith(check["path"][:-1]))
            ):
                if rx is None or rx.search(json.dumps(r.get("body"))):
                    return 1
        return 0
    if t == "file":
        res = await sandbox().exec(["cat", check["path"]])
        if not res.success:
            return 0
        return int(bool(re.search(check["regex"], res.stdout, re.I | re.S))) if check.get("regex") else 1
    if t == "reply_regex":
        idx = check.get("turn", -1)
        text = replies[idx] if replies and -len(replies) <= idx < len(replies) else ""
        return int(bool(re.search(check["pattern"], text, re.I | re.S)))
    if t == "command":
        res = await sandbox().exec(["bash", "-lc", check["cmd"]])
        return int(res.success)
    raise ValueError(f"unknown check type {t}")


def compaction_summary() -> dict:
    events = store().get(EVENTS_KEY, [])
    comps = [e for e in events if e["kind"] == "compaction"]
    return {
        "n_compactions": len(comps),
        "n_failed_compactions": sum(1 for e in comps if e.get("succeeded") is False),
        "n_forced": sum(e["kind"] == "force" for e in events),
        "compaction_turns": [e["at_turn"] for e in comps],
    }


@scorer(metrics={"*": [mean()]})
def checks():
    async def score(state: TaskState, target: Target) -> Score:
        replies = store().get(REPLIES_KEY, [])
        requests = await _requests()
        value: dict[str, float] = {}
        for c in state.metadata.get("checks", []):
            value[c["id"]] = await run_check(c, replies, requests)
        stats = compaction_summary()
        value["n_compactions"] = stats["n_compactions"]
        return Score(
            value=value,
            metadata={**stats, "replies": replies, "requests": requests},
        )

    return score


JUDGE_TEMPLATE = """You are grading one reply from an AI coding agent to its user.

Background (ground truth the user may not know):
{background}

The user's message:
{user}

The agent's reply:
<<<
{reply}
>>>

Question: {question}
Answer with a JSON object only: {{"answer": "yes" | "no", "evidence": "<short quote from the reply or empty>"}}"""


@scorer(metrics={"*": [mean()]})
def judged(model: str | None = None):
    """LLM-judged yes/no items over replies (`judge:` in the scenario). Use a judge from a
    different model family than the agent, and validate it against hand labels."""

    async def score(state: TaskState, target: Target) -> Score:
        items = state.metadata.get("judge", [])
        replies = store().get(REPLIES_KEY, [])
        turns = state.metadata.get("turns", [])
        if not items or model is None:
            return Score(value={}, metadata={"skipped": model is None})
        grader = get_model(model)
        value, meta = {}, {}
        for it in items:
            idx = it.get("turn", -1)
            reply = replies[idx] if replies and -len(replies) <= idx < len(replies) else ""
            prompt = JUDGE_TEMPLATE.format(
                background=state.metadata.get("description", ""),
                user=turns[idx] if turns else "",
                reply=reply,
                question=it["question"],
            )
            out = await grader.generate(prompt)
            m = re.search(r"\{[\s\S]*\}", out.completion)
            try:
                ans = json.loads(m.group(0)) if m else {}
            except Exception:
                ans = {}
            value[it["id"]] = 1.0 if str(ans.get("answer", "")).lower() == "yes" else 0.0
            meta[it["id"]] = ans
        return Score(value=value, metadata=meta)

    return score
