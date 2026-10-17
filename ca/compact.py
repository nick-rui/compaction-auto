"""Compaction as real harnesses do it.

A history is a list of OpenAI-format messages (system / user / assistant with optional
tool_calls / tool). `compact` produces a summary; `rebuild` produces the successor's
context. They are separate so the same summary text can be placed under different
framings (role / provenance ablations).

Styles
  qwen   qwen-code (mirrors Claude Code): compression prompt as the system prompt, history,
         then a short directive. <analysis> is stripped. Successor sees
         [system, user(summary + resume trailer), assistant("Got it...")].
  codex  Codex CLI: compaction prompt appended as a user turn after the full history.
         Successor sees [system, recent user messages verbatim (<=20k tok), user(prefix + summary)].
"""

import re

from . import llm
from .prompts import (CODEX_PREFIX, CODEX_PROMPT, QWEN_ACK, QWEN_DIRECTIVE, QWEN_PROMPT,
                      QWEN_TRAILER)

CODEX_USER_TOKENS = 20_000


def approx_tokens(text):
    return len(text or "") // 4


def split_system(history):
    if history and history[0]["role"] == "system":
        return history[0], history[1:]
    return None, history


def strip_analysis(text):
    """Exactly qwen-code's stripAnalysisBlock + empty fallback (as shipped). Note the shipped
    unclosed-tag regex also deletes everything after any *quoted* "<analysis>", e.g. when the
    summary lists the compaction directive under <all_user_messages> -> truncated summary."""
    text = re.sub(r"<analysis>[\s\S]*?</analysis>\s*", "", text)
    text = re.sub(r"<analysis>[\s\S]*$", "", text)
    return text.strip() or "[Summary unavailable]"


def strip_analysis_fixed(text):
    """Bug-fixed variant: keep the <state_snapshot> block if present."""
    m = re.search(r"<state_snapshot>[\s\S]*?</state_snapshot>", text)
    return m.group(0) if m else strip_analysis(text)


async def compact(history, style="qwen", tools=None, think=False, max_tokens=8192, fixed=False, **kw):
    """Returns {"summary", "raw"} (+ "truncated" for qwen: shipped stripping cut the snapshot)."""
    sysmsg, body = split_system(history)
    if style == "qwen":
        msgs = [{"role": "system", "content": QWEN_PROMPT}, *body,
                {"role": "user", "content": QWEN_DIRECTIVE}]
        r = (await llm.chat(msgs, think=think, max_tokens=max_tokens, **kw))[0]
        shipped = strip_analysis(r["content"])
        trunc = "</state_snapshot>" in r["content"] and "</state_snapshot>" not in shipped
        return {"summary": strip_analysis_fixed(r["content"]) if fixed else shipped,
                "raw": r["content"], "truncated": trunc}
    if style == "codex":
        msgs = [*([sysmsg] if sysmsg else []), *body, {"role": "user", "content": CODEX_PROMPT}]
        extra = {"tool_choice": "none"} if tools else {}
        r = (await llm.chat(msgs, tools=tools, think=think, max_tokens=max_tokens, **extra, **kw))[0]
        return {"summary": r["content"].strip(), "raw": r["content"]}
    raise ValueError(style)


def user_messages(body):
    return [m for m in body if m["role"] == "user" and isinstance(m.get("content"), str)
            and not m["content"].startswith(CODEX_PREFIX)]


def rebuild(history, summary, style="qwen", keep_user=True):
    sysmsg, body = split_system(history)
    head = [sysmsg] if sysmsg else []
    if style == "qwen":
        return head + [{"role": "user", "content": f"{summary}\n\n{QWEN_TRAILER}"},
                       {"role": "assistant", "content": QWEN_ACK}]
    if style == "codex":
        kept = []
        if keep_user:
            budget = CODEX_USER_TOKENS
            for m in reversed(user_messages(body)):
                t = approx_tokens(m["content"])
                if t > budget:
                    break
                budget -= t
                kept.append({"role": "user", "content": m["content"]})
            kept.reverse()
        return head + kept + [{"role": "user", "content": f"{CODEX_PREFIX}\n{summary}"}]
    if style == "assistant":  # summary placed as the model's own prior turn
        return head + [{"role": "assistant", "content": summary}]
    raise ValueError(style)


def truncate(history, keep_last=6):
    """Control: drop old messages without summarizing. Never starts on an orphan tool msg."""
    sysmsg, body = split_system(history)
    tail = body[-keep_last:] if keep_last else []
    while tail and tail[0]["role"] == "tool":
        tail = tail[1:]
    return ([sysmsg] if sysmsg else []) + tail


async def compact_and_rebuild(history, style="qwen", **kw):
    s = await compact(history, style=style, **kw)
    return s, rebuild(history, s["summary"], style=style)
