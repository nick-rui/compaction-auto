"""Scorers: deterministic environment checks, optional LLM-judge items, compaction stats.

Check types (scenario `checks:`):
  request       a mock-service request matching method/path (and optional body_regex)
                was made. {id, type: request, method, path, body_regex?, turn?}; with
                `turn` (index into turns, negative from the end) only requests made while
                that scripted turn was running count
  file          a file exists (and optionally matches `regex`). {id, type: file, path, regex?}
  reply_regex   the reply to turn `turn` (default -1) matches `pattern` (case-insensitive).
  command       a shell command in the sandbox exits 0. {id, type: command, cmd}
Each check scores 1/0; the Score value is a dict {check_id: 0|1, ..., n_compactions: k}.

Retention (scenario `retain:`): `retain.<id>` is 1 if the pattern was visible anywhere in
the successor's context after the *last* compaction (1 when nothing was compacted: the full
history is present), and `retain_post.<id>` the same for the post-compaction message alone.
Per-round values are in the score metadata under `retention`.
"""

from __future__ import annotations

import json
import re

from inspect_ai.model import get_model
from inspect_ai.scorer import Metric, SampleScore, Score, Target, metric, scorer
from inspect_ai.solver import TaskState
from inspect_ai.util import sandbox, store

from .filter import EVENTS_KEY
from .solver import REPLIES_KEY, TURN_TIMES_KEY


async def _requests() -> list[dict]:
    try:
        raw = await sandbox().read_file("/var/log/ce/requests.jsonl")
    except Exception:
        return []
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def turn_window(turn_times: list[float], turn: int) -> tuple[float, float]:
    """[start, end) epoch seconds of scripted turn `turn` (negative indexes from the end)."""
    if not turn_times or not -len(turn_times) <= turn < len(turn_times):
        return (float("inf"), float("inf"))  # turn never ran: nothing matches
    i = turn % len(turn_times)
    end = turn_times[i + 1] if i + 1 < len(turn_times) else float("inf")
    return turn_times[i], end


async def run_check(
    check: dict, replies: list[str], requests: list[dict], turn_times: list[float] | None = None
) -> int:
    t = check["type"]
    if t == "request":
        rx = re.compile(check["body_regex"], re.I | re.S) if check.get("body_regex") else None
        if check.get("turn") is not None:
            lo, hi = turn_window(turn_times or [], int(check["turn"]))
            requests = [r for r in requests if lo <= r.get("t", lo - 1) < hi]
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


def retention_summary(patterns: list[dict]) -> tuple[dict[str, int], dict[str, list]]:
    events = [e for e in store().get(EVENTS_KEY, []) if e["kind"] == "retention"]
    value: dict[str, int] = {}
    for p in patterns:
        last = events[-1] if events else None
        value[f"retain.{p['id']}"] = last["in_context"].get(p["id"], 0) if last else 1
        value[f"retain_post.{p['id']}"] = last["in_post"].get(p["id"], 0) if last else 1
    rounds = {"in_context": [e["in_context"] for e in events], "in_post": [e["in_post"] for e in events]}
    return value, rounds


def compaction_summary() -> dict:
    events = store().get(EVENTS_KEY, [])
    comps = [e for e in events if e["kind"] == "compaction"]
    return {
        "n_compactions": len(comps),
        "n_failed_compactions": sum(1 for e in comps if e.get("succeeded") is False),
        "n_forced": sum(e["kind"] == "force" for e in events),
        "compaction_turns": [e["at_turn"] for e in comps],
        "compaction_user_turns": [e.get("user_turn") for e in comps],
    }


@metric
def mean_by_key() -> Metric:
    """Mean of each key over the samples whose score has it. Scenarios have different check
    ids, and Inspect's {"*": [mean()]} raises when a key is missing from some samples."""

    def compute(scores: list[SampleScore]) -> dict[str, float]:
        sums: dict[str, list[float]] = {}
        for s in scores:
            v = s.score.value
            if isinstance(v, dict):
                for k, x in v.items():
                    if isinstance(x, (int, float)):
                        sums.setdefault(k, []).append(float(x))
        return {k: sum(xs) / len(xs) for k, xs in sums.items()}

    return compute


@scorer(metrics=[mean_by_key()])
def checks():
    async def score(state: TaskState, target: Target) -> Score:
        replies = store().get(REPLIES_KEY, [])
        requests = await _requests()
        turn_times = store().get(TURN_TIMES_KEY, [])
        value: dict[str, float] = {}
        for c in state.metadata.get("checks", []):
            value[c["id"]] = await run_check(c, replies, requests, turn_times)
        retained, rounds = retention_summary(state.metadata.get("retain", []))
        value.update(retained)
        stats = compaction_summary()
        value["n_compactions"] = stats["n_compactions"]
        return Score(
            value=value,
            metadata={**stats, "replies": replies, "requests": requests,
                      "turn_times": turn_times, "retention": rounds},
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


@scorer(metrics=[mean_by_key()])
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
