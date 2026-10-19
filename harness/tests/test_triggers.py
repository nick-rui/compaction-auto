"""at_user_turns trigger, retention detection and turn-scoped request windows."""

from inspect_ai.model import ChatMessageAssistant, ChatMessageTool, ChatMessageUser
from inspect_ai.tool import ToolCall

from ce.filter import retention_hits, user_turn_force
from ce.policies import build_policy
from ce.policy import CompactionCounters, Trigger
from ce.scorers import turn_window


def _compact(c: CompactionCounters) -> None:
    """What the filter does when a compaction request arrives."""
    c.compactions += 1
    if c.pending_user_turn is not None:
        c.user_turns_done.append(c.pending_user_turn)
        c.pending_user_turn = None


def test_boundary_force_on_turn_ending_output():
    trig = Trigger(mode="at_user_turns", user_turns=(1, 2))
    c = CompactionCounters()
    assert user_turn_force(trig, c, 0, ends_turn=False) is None  # tool call inside turn 0
    assert user_turn_force(trig, c, 0, ends_turn=True) == "boundary"
    assert c.pending_user_turn == 1
    _compact(c)  # harness compacts before turn 1's first call
    assert user_turn_force(trig, c, 1, ends_turn=False) is None  # no fallback: already done
    assert user_turn_force(trig, c, 1, ends_turn=True) == "boundary"
    _compact(c)
    assert user_turn_force(trig, c, 2, ends_turn=True) is None  # turn 3 not listed
    assert c.user_turns_done == [1, 2]


def test_fallback_when_harness_ignores_boundary():
    trig = Trigger(mode="at_user_turns", user_turns=(1,))
    c = CompactionCounters()
    assert user_turn_force(trig, c, 0, ends_turn=True) == "boundary"
    # no compaction happened; first agent call of turn 1 forces again
    assert user_turn_force(trig, c, 1, ends_turn=False) == "fallback"
    _compact(c)
    assert c.user_turns_done == [1]
    assert user_turn_force(trig, c, 1, ends_turn=False) is None


def test_max_compactions_caps_user_turns():
    trig = Trigger(mode="at_user_turns", user_turns=(1, 2), max_compactions=1)
    c = CompactionCounters()
    assert user_turn_force(trig, c, 0, ends_turn=True) == "boundary"
    _compact(c)
    assert user_turn_force(trig, c, 1, ends_turn=True) is None


def test_build_policy_parses_user_turns():
    p = build_policy(trigger="at_user_turns", user_turns="1,2,4")
    assert p.trigger.mode == "at_user_turns" and tuple(p.trigger.user_turns) == (1, 2, 4)
    assert p.describe()["trigger_user_turns"] == [1, 2, 4]
    assert tuple(build_policy(trigger="at_user_turns", user_turns=3).trigger.user_turns) == (3,)
    # what `inspect eval -T user_turns=1,2,3` actually passes
    assert tuple(build_policy(trigger="at_user_turns", user_turns=["1", "2", "3"]).trigger.user_turns) == (1, 2, 3)
    assert tuple(build_policy(trigger="at_turns", turns=["3", "8"]).trigger.turns) == (3, 8)


def test_retention_hits_context_vs_post():
    msgs = [
        ChatMessageUser(content="summary without the fact"),
        ChatMessageAssistant(content="", tool_calls=[ToolCall(id="1", function="bash",
                                                              arguments={"cmd": "cat ticket-881.md"})]),
        ChatMessageTool(content="Invoice #881 was already paid", tool_call_id="1"),
    ]
    pats = [{"id": "paid", "pattern": r"#?881.{0,40}paid"}, {"id": "marco", "pattern": "marco"}]
    in_ctx, in_post = retention_hits(msgs, [0], pats)
    assert in_ctx == {"paid": 1, "marco": 0}
    assert in_post == {"paid": 0, "marco": 0}
    assert retention_hits(msgs, [], [{"id": "args", "pattern": "ticket-881"}])[0] == {"args": 1}


def test_turn_window():
    times = [100.0, 200.0, 300.0]
    assert turn_window(times, 0) == (100.0, 200.0)
    assert turn_window(times, -1) == (300.0, float("inf"))
    assert turn_window(times, 5) == (float("inf"), float("inf"))
    assert turn_window([], -1) == (float("inf"), float("inf"))
