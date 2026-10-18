"""Compaction policy: everything an experiment can control about compaction.

Three layers, matching how real harnesses work:

  pre      the instructions the summarizing model gets (the harness's compaction prompt)
  post     the message that carries the summary into the next context (wrapper + summary)
  trigger  when compaction happens

Pre/post control works by rewriting bridged requests (harness-agnostic). Trigger control
uses the harness's own auto-compact logic: either its native threshold, or a schedule that
makes the harness *decide* to compact by reporting context usage above that threshold.
Nothing here replaces harness logic; the harness still builds the compaction request and
the rebuilt context itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Sequence

from inspect_ai.model import ChatMessage

# A predicate over the conversation so far (after the latest model output). Returning True
# schedules a compaction before the harness's next model call.
EventPredicate = Callable[[list[ChatMessage], "CompactionCounters"], bool]


@dataclass
class CompactionCounters:
    turns: int = 0  # normal (non-compaction) model calls so far
    turns_since_compaction: int = 0
    compactions: int = 0
    last_input_tokens: int = 0


@dataclass
class Trigger:
    """When to compact.

    mode:
      native       leave it to the harness's threshold (`window_tokens`, see below)
      every_n      force a compaction after every `n` normal model calls
      at_turns     force a compaction after the listed normal-call indices (1-based)
      on_event     force a compaction when `predicate(messages, counters)` is True
      never        report low usage so the harness never auto-compacts
    window_tokens: the context window the harness is told it has; its native auto-compact
      threshold is derived from this (Claude Code: CLAUDE_CODE_AUTO_COMPACT_WINDOW; Codex:
      model_context_window + model_auto_compact_token_limit). None = harness default.
    max_compactions: stop forcing after this many compactions (None = unlimited).
    """

    mode: Literal["native", "every_n", "at_turns", "on_event", "never"] = "native"
    window_tokens: int | None = None
    n: int = 10
    turns: Sequence[int] = ()
    predicate: EventPredicate | None = None
    max_compactions: int | None = None


@dataclass
class PrePrompt:
    """Pre-compaction prompt control.

    mode:
      harness   leave the harness's own compaction prompt
      replace   replace it with `text`
      append    append `text` after it
      prepend   put `text` before it
    """

    mode: Literal["harness", "replace", "append", "prepend"] = "harness"
    text: str = ""


@dataclass
class PostPrompt:
    """Post-compaction message control.

    mode:
      harness   leave the harness's wrapper
      template  replace the whole post-compaction message with `template.format(summary=...)`
      wrap      keep the harness wrapper, but add `prefix` before and `suffix` after it
    summary_transform: optional function applied to the summary text before it is placed
      (e.g. delete a sentence, insert a planted note). Applied in every mode.
    """

    mode: Literal["harness", "template", "wrap"] = "harness"
    template: str = "{summary}"
    prefix: str = ""
    suffix: str = ""
    summary_transform: Callable[[str], str] | None = None


@dataclass
class CompactionPolicy:
    name: str = "harness_default"
    pre: PrePrompt = field(default_factory=PrePrompt)
    post: PostPrompt = field(default_factory=PostPrompt)
    trigger: Trigger = field(default_factory=Trigger)
    # route compaction calls to a different Inspect model (None = the agent's model)
    summarizer_model: str | None = None
    # merge/relocate system messages for strict open-model chat templates (see filter.py)
    normalize_system: bool = True
    # extra harness env vars / config overrides an experiment wants (merged last)
    extra_env: dict[str, str] = field(default_factory=dict)
    extra_config: dict[str, str] = field(default_factory=dict)

    def describe(self) -> dict:
        return {
            "policy": self.name,
            "pre_mode": self.pre.mode,
            "post_mode": self.post.mode,
            "post_transform": self.post.summary_transform is not None,
            "trigger": self.trigger.mode,
            "window_tokens": self.trigger.window_tokens,
            "trigger_n": self.trigger.n if self.trigger.mode == "every_n" else None,
            "trigger_turns": list(self.trigger.turns) or None,
            "max_compactions": self.trigger.max_compactions,
            "summarizer_model": self.summarizer_model,
        }
