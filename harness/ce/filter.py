"""Bridge filter that applies a CompactionPolicy to a real harness's model traffic.

The filter sees every model call the harness makes (after the Inspect bridge has turned it
into ChatMessages) and:

  * classifies it (compaction request / normal call),
  * rewrites the pre-compaction prompt and every post-compaction message per the policy,
  * routes compaction calls to `policy.summarizer_model` if set,
  * adjusts the *reported* input-token usage on agent calls so the harness's own
    auto-compact logic fires when the trigger schedule says so (or never fires),
  * records compaction events in the sample store (`ce_events`) for scoring/analysis.

The model always sees the rewritten input, so ModelEvents in the Inspect log show exactly
what the model was given.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from typing import Any

from inspect_ai.log import transcript
from inspect_ai.model import (
    ChatMessage,
    ChatMessageSystem,
    ChatMessageUser,
    GenerateConfig,
    GenerateInput,
    Model,
    ModelOutput,
    get_model,
)
from inspect_ai.tool import ToolChoice, ToolInfo
from inspect_ai.util import store

from .policy import CompactionCounters, CompactionPolicy, PostPrompt, PrePrompt
from .signatures import (
    SIGNATURES,
    HarnessSignature,
    compaction_prompt_index,
    message_text,
    post_message_indices,
    replace_user_text,
    split_post_message,
)

EVENTS_KEY = "ce_events"
COUNTERS_KEY = "ce_counters"
SEEN_POSTS_KEY = "ce_seen_posts"

# Reported input tokens when forcing a compaction (if the policy gives no window) and when
# suppressing one.
DEFAULT_WINDOW = {"claude_code": 200_000, "codex_cli": 200_000}
SUPPRESSED_USAGE = 1_000


def normalize_system_messages(msgs: list[ChatMessage]) -> list[ChatMessage]:
    """Make system messages acceptable to strict chat templates (e.g. Qwen's).

    Harnesses send several system blocks (Claude Code) or mid-conversation developer
    messages (Codex re-injects instructions after compaction). Many open-model templates
    accept a single leading system message only. Leading system messages are merged in
    order; later ones become user messages tagged <system-message>, keeping their position.
    """
    lead: list[str] = []
    i = 0
    while i < len(msgs) and isinstance(msgs[i], ChatMessageSystem):
        lead.append(message_text(msgs[i]))
        i += 1
    rest = [
        ChatMessageUser(content=f"<system-message>\n{message_text(m)}\n</system-message>")
        if isinstance(m, ChatMessageSystem)
        else m
        for m in msgs[i:]
    ]
    if len(lead) <= 1 and all(r is m for r, m in zip(rest, msgs[i:])):
        return msgs
    head = [ChatMessageSystem(content="\n\n".join(lead))] if lead else []
    return head + rest


def _h(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def apply_pre(text: str, pre: PrePrompt) -> str:
    if pre.mode == "replace":
        return pre.text
    if pre.mode == "append":
        return f"{text}\n\n{pre.text}"
    if pre.mode == "prepend":
        return f"{pre.text}\n\n{text}"
    return text


def apply_post(text: str, post: PostPrompt, sig: HarnessSignature) -> tuple[str, str]:
    """Return (new_message_text, summary_as_placed)."""
    parts = split_post_message(text, sig)
    if parts is None:
        return text, ""
    before, summary, after = parts
    if post.summary_transform is not None:
        summary = post.summary_transform(summary)
    if post.mode == "template":
        return post.template.format(summary=summary), summary
    new = before + summary + after
    if post.mode == "wrap":
        new = f"{post.prefix}{new}{post.suffix}"
    return new, summary


def with_reported_input_tokens(output: ModelOutput, tokens: int) -> ModelOutput:
    """Copy of `output` whose usage reports `tokens` input tokens (what the harness sees)."""
    if output.usage is None:
        return output
    u = output.usage.model_copy(
        update={
            "input_tokens": tokens,
            "input_tokens_cache_read": 0,
            "input_tokens_cache_write": 0,
            "total_tokens": tokens + output.usage.output_tokens,
        }
    )
    return output.model_copy(update={"usage": u})


def load_counters() -> CompactionCounters:
    return CompactionCounters(**store().get(COUNTERS_KEY, {}))


def save_counters(c: CompactionCounters) -> None:
    store().set(COUNTERS_KEY, asdict(c))


def record_event(kind: str, **data: Any) -> None:
    ev = {"kind": kind, **data}
    events = store().get(EVENTS_KEY, [])
    events.append(ev)
    store().set(EVENTS_KEY, events)
    brief = {k: (v if not isinstance(v, str) or len(v) < 300 else v[:300] + "…") for k, v in ev.items()}
    transcript().info(brief, source="ce")


def compaction_filter(policy: CompactionPolicy, harness: str):
    sig = SIGNATURES[harness]
    trig = policy.trigger
    force_tokens = trig.window_tokens or DEFAULT_WINDOW[harness]
    tags = {"harness": harness, "policy": policy.name}

    def should_force(msgs: list[ChatMessage], c: CompactionCounters) -> bool:
        if trig.max_compactions is not None and c.compactions >= trig.max_compactions:
            return False
        if trig.mode == "every_n":
            return c.turns_since_compaction >= trig.n
        if trig.mode == "at_turns":
            return c.turns in set(trig.turns)
        if trig.mode == "on_event" and trig.predicate is not None:
            return bool(trig.predicate(msgs, c))
        return False

    async def filt(
        model: Model,
        messages: list[ChatMessage],
        tools: list[ToolInfo],
        tool_choice: ToolChoice | None,
        config: GenerateConfig,
    ) -> ModelOutput | GenerateInput | None:
        c = load_counters()
        msgs = normalize_system_messages(list(messages)) if policy.normalize_system else list(messages)

        # --- post-compaction messages: rewritten on every call, deterministically ---
        seen = store().get(SEEN_POSTS_KEY, [])
        for i in post_message_indices(msgs, sig):
            original = message_text(msgs[i])
            new_text, placed = apply_post(original, policy.post, sig)
            if new_text != original:
                msgs[i] = replace_user_text(msgs[i], new_text)
            if _h(original) not in seen:
                seen.append(_h(original))
                store().set(SEEN_POSTS_KEY, seen)
                record_event(
                    "post",
                    **tags,
                    index=c.compactions,
                    original_message=original,
                    placed_message=new_text,
                    placed_summary=placed,
                    rewritten=new_text != original,
                )

        # --- compaction requests ---
        i = compaction_prompt_index(msgs, sig)
        if i is not None:
            original = message_text(msgs[i])
            new_text = apply_pre(original, policy.pre)
            if new_text != original:
                msgs[i] = replace_user_text(msgs[i], new_text)
            gen_model = get_model(policy.summarizer_model) if policy.summarizer_model else model
            output = await gen_model.generate(msgs, tools, tool_choice, config)
            c.compactions += 1
            c.turns_since_compaction = 0
            save_counters(c)
            record_event(
                "compaction",
                **tags,
                index=c.compactions,
                at_turn=c.turns,
                last_input_tokens=c.last_input_tokens,
                n_messages=len(msgs),
                original_prompt=original,
                prompt=new_text,
                rewritten=new_text != original,
                summarizer=str(gen_model),
                summary=output.completion,
                stop_reason=output.stop_reason,
                # a compaction "succeeds" if the model wrote text and called no tools; open
                # models sometimes ignore the harness's TEXT ONLY instruction
                succeeded=bool(output.completion.strip()) and not output.message.tool_calls,
                output_tokens=output.usage.output_tokens if output.usage else None,
            )
            return output

        # --- normal calls ---
        is_agent_call = len(tools) > 0  # side calls (titles, classifiers) carry no tools
        if is_agent_call:
            c.turns += 1
            c.turns_since_compaction += 1

        if not is_agent_call or trig.mode == "native":
            save_counters(c)
            if msgs == list(messages):
                return None  # unchanged: let the bridge generate as usual
            return GenerateInput(msgs, tools, tool_choice, config)

        # trigger control: generate here so we can set the usage the harness sees
        output = await model.generate(msgs, tools, tool_choice, config)
        if output.usage is not None:
            c.last_input_tokens = output.usage.input_tokens
        save_counters(c)
        if trig.mode != "never" and should_force(msgs + [output.message], c):
            record_event("force", **tags, at_turn=c.turns, reported_tokens=force_tokens)
            return with_reported_input_tokens(output, force_tokens)
        # otherwise keep the harness below its threshold so only the schedule compacts
        return with_reported_input_tokens(output, SUPPRESSED_USAGE)

    return filt
