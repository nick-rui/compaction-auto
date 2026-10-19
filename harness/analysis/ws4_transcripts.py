"""Turn-by-turn transcripts of WS4 runs, as JSON (for reading, not for scoring).

    python analysis/ws4_transcripts.py runs/ws4/sol1 > runs/ws4/sol1/transcripts.json

One record per sample: config, check scores, and per scripted user turn the agent's
messages and tool calls (with truncated tool output), plus every compaction (which turn it
preceded, the summary, the post-compaction message and retention). Rebuilt from the
sample's model events, so it shows what happened in order, not just the final context.
"""

from __future__ import annotations

import bisect
import json
import sys
from pathlib import Path

from inspect_ai.log import list_eval_logs, read_eval_log
from inspect_ai.model import ChatMessageTool

TOOL_OUT = 700  # chars of tool output kept per call


def _args(tc) -> str:
    a = tc.arguments or {}
    for k in ("command", "cmd"):
        if isinstance(a.get(k), str):
            return a[k]
    return json.dumps(a)[:1500]


def sample_record(log, s) -> dict:
    md = s.metadata or {}
    checks = (s.scores or {}).get("checks")
    cm = checks.metadata if checks else {}
    turn_times = cm.get("turn_times", [])
    turns = [{"user": u, "steps": [], "reply": r}
             for u, r in zip(md.get("turns", []), cm.get("replies", []) + [""] * 20)]
    events = (s.store or {}).get("ce_events", [])
    comps = [e for e in events if e["kind"] == "compaction"]
    posts = {e["index"]: e for e in events if e["kind"] == "post"}
    ret = {e["index"]: e for e in events if e["kind"] == "retention"}
    summaries = {e["summary"].strip()[:200] for e in comps}
    n_tool_msgs_seen = 0
    for e in s.events:
        if e.event != "model" or not e.tools:
            continue  # judge calls and harness side calls (titles etc.) carry no tools
        out = e.output.message
        text = (e.output.completion or "").strip()
        if text[:200] in summaries:
            continue  # the compaction call itself; shown in `compactions`
        t = e.timestamp.timestamp() if e.timestamp else 0.0
        ti = max(0, bisect.bisect_right(turn_times, t) - 1) if turn_times else 0
        if ti >= len(turns):
            continue
        # tool results that arrived since the previous call, attached to the previous step's calls
        tool_msgs = [m for m in e.input if isinstance(m, ChatMessageTool)]
        new = tool_msgs[n_tool_msgs_seen:] if len(tool_msgs) >= n_tool_msgs_seen else tool_msgs
        n_tool_msgs_seen = len(tool_msgs)
        if new and turns[ti]["steps"]:
            prev = turns[ti]["steps"][-1]
            for c, m in zip([c for c in prev.get("calls", []) if c.get("out") is None], new):
                c["out"] = m.text[:TOOL_OUT]
        step = {}
        if text:
            step["text"] = text[:2500]
        if out.tool_calls:
            step["calls"] = [{"fn": tc.function, "args": _args(tc), "out": None} for tc in out.tool_calls]
        if step:
            turns[ti]["steps"].append(step)
    return {
        "log": Path(log.location).name,
        "scenario": md.get("scenario"),
        "harness": md.get("harness"),
        "trigger": md.get("trigger"),
        "user_turns": md.get("trigger_user_turns"),
        "R": len(md.get("trigger_user_turns") or []) if md.get("trigger") == "at_user_turns" else 0,
        "error": s.error.message[:500] if s.error else None,
        "scores": {k: v.value for k, v in (s.scores or {}).items()},
        "judge": (s.scores or {}).get("judged").metadata if (s.scores or {}).get("judged") else None,
        "n_agent_calls": sum(1 for e in s.events if e.event == "model" and e.tools),
        "turns": turns,
        "compactions": [{
            "index": c["index"], "before_turn": c.get("user_turn"), "at_call": c["at_turn"],
            "succeeded": c.get("succeeded"), "summary": c["summary"],
            "post_message": (posts.get(c["index"]) or {}).get("placed_message"),
            "retention": {k: v for k, v in (ret.get(c["index"]) or {}).items() if k in ("in_context", "in_post")},
        } for c in comps],
    }


def main(dirs: list[str]) -> None:
    recs = []
    for d in dirs:
        # one log per run directory: the newest successful one (an eval-retry writes a new log
        # next to the failed original and carries its completed samples over), else the newest
        by_dir: dict[str, list] = {}
        for info in list_eval_logs(d, recursive=True):
            by_dir.setdefault(str(Path(info.name).parent), []).append(info)
        for infos in by_dir.values():
            heads = sorted(((read_eval_log(i, header_only=True), i) for i in infos),
                           key=lambda h: h[0].eval.created, reverse=True)
            ok = [i for h, i in heads if h.status == "success"]
            log = read_eval_log(ok[0] if ok else heads[0][1], resolve_attachments=True)
            recs.extend(sample_record(log, s) for s in log.samples or [])
    recs.sort(key=lambda r: (r["scenario"] or "", r["harness"] or "", r["R"]))
    json.dump(recs, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
