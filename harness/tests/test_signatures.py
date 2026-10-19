"""Detectors and rewrites, checked against recorded harness traffic (goldens/)."""

from pathlib import Path

import pytest
from inspect_ai.model import ChatMessageAssistant, ChatMessageSystem, ChatMessageUser

from ce.filter import apply_post, apply_pre, normalize_system_messages
from ce.policy import PostPrompt, PrePrompt
from ce.signatures import (
    SIGNATURES,
    compaction_prompt_index,
    post_message_indices,
    split_post_message,
)

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
CASES = [
    (h, v.name)
    for h in sorted(SIGNATURES)
    for v in sorted((GOLDENS / h).glob("*"))
    if (GOLDENS / h).exists()
]


@pytest.mark.parametrize("harness,version", CASES)
def test_golden_compaction_prompt_detected(harness, version):
    sig = SIGNATURES[harness]
    prompt = (GOLDENS / harness / version / "compaction_prompt.txt").read_text()
    msgs = [ChatMessageUser(content="do the task"), ChatMessageAssistant(content="ok"),
            ChatMessageUser(content=prompt), ChatMessageUser(content="<system-message>reminder</system-message>")]
    assert compaction_prompt_index(msgs, sig) == 2


@pytest.mark.parametrize("harness,version", CASES)
def test_golden_post_message_split(harness, version):
    sig = SIGNATURES[harness]
    post = (GOLDENS / harness / version / "post_message.txt").read_text()
    parts = split_post_message(post, sig)
    assert parts is not None
    before, summary, after = parts
    assert before + summary + after == post
    assert len(summary) > 50
    if harness == "claude_code":
        assert before.rstrip().endswith("Summary:")
        assert "read the full transcript" not in summary
        assert "Continue the conversation from where it left off" not in summary
    # the post message must not be mistaken for a compaction request
    assert compaction_prompt_index([ChatMessageUser(content=post)], sig) is None


@pytest.mark.parametrize("harness,version", CASES)
def test_post_rewrites(harness, version):
    sig = SIGNATURES[harness]
    post = (GOLDENS / harness / version / "post_message.txt").read_text()
    _, summary, _ = split_post_message(post, sig)
    new, placed = apply_post(post, PostPrompt(mode="template", template="S::{summary}"), sig)
    assert new == "S::" + summary and placed == summary
    new, _ = apply_post(post, PostPrompt(mode="harness", summary_transform=lambda s: s + "\nPLANTED"), sig)
    assert "PLANTED" in new and new.replace("\nPLANTED", "") == post
    new, _ = apply_post(post, PostPrompt(mode="wrap", prefix="<<", suffix=">>"), sig)
    assert new == "<<" + post + ">>"
    msgs = [ChatMessageUser(content="x"), ChatMessageUser(content=post)]
    assert post_message_indices(msgs, sig) == [1]


def test_apply_pre_modes():
    assert apply_pre("A", PrePrompt(mode="harness")) == "A"
    assert apply_pre("A", PrePrompt(mode="replace", text="B")) == "B"
    assert apply_pre("A", PrePrompt(mode="append", text="B")) == "A\n\nB"
    assert apply_pre("A", PrePrompt(mode="prepend", text="B")) == "B\n\nA"


def test_normalize_system_messages():
    msgs = [ChatMessageSystem(content="s1"), ChatMessageSystem(content="s2"),
            ChatMessageUser(content="u"), ChatMessageSystem(content="late")]
    out = normalize_system_messages(msgs)
    assert [m.role for m in out] == ["system", "user", "user"]
    assert out[0].text == "s1\n\ns2"
    assert "late" in out[2].text
    single = [ChatMessageSystem(content="s"), ChatMessageUser(content="u")]
    assert normalize_system_messages(single) is single


@pytest.mark.parametrize("harness,version", CASES)
def test_summary_append_cli(harness, version):
    from ce.policies import build_policy
    sig = SIGNATURES[harness]
    post = (GOLDENS / harness / version / "post_message.txt").read_text()
    pol = build_policy("harness_default", summary_append="PLANTED NOTE", summary_prepend="TOP NOTE")
    new, placed = apply_post(post, pol.post, sig)
    assert "PLANTED NOTE" in placed and placed.lstrip().startswith("TOP NOTE")
    before, _, after = split_post_message(post, sig)
    assert new.startswith(before) and new.endswith(after)
