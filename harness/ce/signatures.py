"""Recognise compaction traffic for each real harness.

Every model call from a harness passes through the Inspect agent bridge as a list of
Inspect ChatMessages. A call is one of three kinds:

  compaction  the harness is asking the model to write a summary (its pre-compaction
              prompt is the last user message)
  post        an ordinary call whose context contains the harness's post-compaction
              message (wrapper + summary)
  normal      anything else

Signatures are taken from the harnesses' shipped prompt text (Codex: codex-rs/prompts/
templates/compact/*.md; Claude Code: closed source, text observed in recorded traffic).
`scripts/capture_goldens.py` records real traffic so these can be checked and updated
when a harness version changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from inspect_ai.model import ChatMessage, ChatMessageAssistant, ChatMessageUser, ContentText


@dataclass(frozen=True)
class HarnessSignature:
    harness: str
    # substrings that identify the pre-compaction prompt (any match)
    compaction_markers: tuple[str, ...]
    # regex over the post-compaction message text; must define a `summary` group
    post_pattern: re.Pattern[str]


CODEX_SUMMARY_PREFIX = (
    "Another language model started to solve this problem and produced a summary of its "
    "thinking process. You also have access to the state of the tools that were used by "
    "that language model. Use this to build on the work that has already been done and "
    "avoid duplicating work. Here is the summary produced by the other language model, "
    "use the information in this summary to assist with your own analysis:"
)

CLAUDE_POST_PREFIX = (
    "This session is being continued from a previous conversation that ran out of context."
)

SIGNATURES: dict[str, HarnessSignature] = {
    "codex_cli": HarnessSignature(
        harness="codex_cli",
        compaction_markers=("You are performing a CONTEXT CHECKPOINT COMPACTION",),
        post_pattern=re.compile(re.escape(CODEX_SUMMARY_PREFIX) + r"\n?(?P<summary>[\s\S]*)\Z"),
    ),
    "claude_code": HarnessSignature(
        harness="claude_code",
        # Verified against Claude Code 2.1.292 traffic (see goldens/). The prompt is preceded
        # by "CRITICAL: Respond with TEXT ONLY..." and asks for <analysis> + <summary>.
        compaction_markers=(
            "Your task is to create a detailed summary of the conversation so far",
            "This conversation is being compacted",
            "Write a continuation summary that will allow you",
        ),
        # Post message (one user turn, after a <system-reminder> gitStatus block):
        #   "This session is being continued ... earlier portion of the conversation.\n\n"
        #   "Summary:\n" <summary>
        #   "\n\nIf you need specific details from before compaction ... read the full transcript at: <path>\n"
        #   "Continue the conversation from where it left off ... as if the break never happened."
        post_pattern=re.compile(
            re.escape(CLAUDE_POST_PREFIX)
            + r"[^\n]*\n+Summary:[ \t]*\n(?P<summary>[\s\S]*?)"
            + r"(?=\n+(?:If you need specific details from before compaction|"
            + r"Continue the conversation from where it left off)|\Z)"
        ),
    ),
}


def message_text(m: ChatMessage) -> str:
    return m.text if isinstance(m.content, list) else (m.content or "")


def last_user_index(messages: list[ChatMessage]) -> int | None:
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], ChatMessageUser):
            return i
    return None


def compaction_prompt_index(messages: list[ChatMessage], sig: HarnessSignature) -> int | None:
    """Index of the user message carrying the pre-compaction prompt, if this is a
    compaction request. Only the trailing user turn(s) are checked (harnesses append
    reminders as extra user/system messages after the prompt)."""
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, ChatMessageAssistant):
            return None
        if isinstance(m, ChatMessageUser) and any(mk in message_text(m) for mk in sig.compaction_markers):
            return i
    return None


def is_compaction_request(messages: list[ChatMessage], sig: HarnessSignature) -> bool:
    return compaction_prompt_index(messages, sig) is not None


def post_message_indices(messages: list[ChatMessage], sig: HarnessSignature) -> list[int]:
    return [
        i
        for i, m in enumerate(messages)
        if isinstance(m, ChatMessageUser) and sig.post_pattern.search(message_text(m))
    ]


def split_post_message(text: str, sig: HarnessSignature) -> tuple[str, str, str] | None:
    """Return (before, summary, after) for a post-compaction message, or None."""
    m = sig.post_pattern.search(text)
    if not m:
        return None
    s, e = m.span("summary")
    return text[:s], text[s:e], text[e:]


def replace_user_text(m: ChatMessage, new_text: str) -> ChatMessage:
    """Return a copy of a user message with its text replaced (non-text parts kept)."""
    if isinstance(m.content, str):
        return m.model_copy(update={"content": new_text})
    parts, done = [], False
    for c in m.content:
        if isinstance(c, ContentText):
            if not done:
                parts.append(c.model_copy(update={"text": new_text}))
                done = True
        else:
            parts.append(c)
    if not done:
        parts.insert(0, ContentText(text=new_text))
    return m.model_copy(update={"content": parts})
