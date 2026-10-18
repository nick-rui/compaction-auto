"""Load eval logs into tidy DataFrames.

    from ce.analysis import samples_df, compactions_df
    df = samples_df("runs/grid")          # one row per sample: config + check scores
    comps = compactions_df("runs/grid")   # one row per compaction: prompt, summary, timing
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from inspect_ai.log import list_eval_logs, read_eval_log

CONFIG_KEYS = ("harness", "policy", "pre_mode", "post_mode", "post_transform", "trigger",
               "window_tokens", "trigger_n", "trigger_turns", "max_compactions", "summarizer_model")


def _logs(path: str | Path):
    for info in list_eval_logs(str(path)):
        yield read_eval_log(info, resolve_attachments=True)


def samples_df(path: str | Path) -> pd.DataFrame:
    rows = []
    for log in _logs(path):
        for s in log.samples or []:
            md = s.metadata or {}
            row = {"log": Path(log.location).name, "model": log.eval.model, "sample": s.id,
                   "epoch": s.epoch, "scenario": md.get("scenario"), "error": bool(s.error)}
            row.update({k: md.get(k) for k in CONFIG_KEYS})
            for name, sc in (s.scores or {}).items():
                if isinstance(sc.value, dict):
                    row.update({f"{name}.{k}": v for k, v in sc.value.items()})
                else:
                    row[name] = sc.value
            rows.append(row)
    return pd.DataFrame(rows)


def compactions_df(path: str | Path) -> pd.DataFrame:
    rows = []
    for log in _logs(path):
        for s in log.samples or []:
            md = s.metadata or {}
            posts = [e for e in (s.store or {}).get("ce_events", []) if e["kind"] == "post"]
            for e in (s.store or {}).get("ce_events", []):
                if e["kind"] != "compaction":
                    continue
                post = next((p for p in posts if p.get("index") == e["index"]), None)
                rows.append({
                    "log": Path(log.location).name, "sample": s.id, "epoch": s.epoch,
                    "scenario": md.get("scenario"), **{k: md.get(k) for k in CONFIG_KEYS},
                    "index": e["index"], "at_turn": e["at_turn"], "rewritten_pre": e["rewritten"],
                    "prompt": e["prompt"], "summary": e["summary"], "stop_reason": e["stop_reason"],
                    "output_tokens": e.get("output_tokens"),
                    "post_message": post["placed_message"] if post else None,
                    "placed_summary": post["placed_summary"] if post else None,
                })
    return pd.DataFrame(rows)
