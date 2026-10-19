"""Scripted multi-turn conversation with a real harness.

turns[0] is the sample input. After the agent finishes a turn, the next scripted user
message is appended and the same harness session is resumed (inspect_swe resumes the
CLI's own session: `claude --resume <id>` / `codex exec resume --last`), so compaction
state carries across user turns exactly as it would for a real user.

The store tracks which scripted turn is running (`ce_turn`, read by the at_user_turns
trigger), when each turn started (`ce_turn_times`, epoch seconds, the clock mock-service
requests are logged with), and the scenario's `retain:` patterns (`ce_retain`, read by the
filter after each compaction).
"""

from __future__ import annotations

import time

from inspect_ai.agent import Agent, AgentState
from inspect_ai.model import ChatMessageUser
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.util import store

REPLIES_KEY = "ce_replies"
TURN_KEY = "ce_turn"
TURN_TIMES_KEY = "ce_turn_times"
RETAIN_KEY = "ce_retain"


@solver
def converse(agent: Agent) -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        turns: list[str] = state.metadata.get("turns") or [state.input_text]
        agent_state = AgentState(messages=list(state.messages))
        replies: list[str] = []
        times: list[float] = []
        store().set(RETAIN_KEY, state.metadata.get("retain") or [])
        for i, turn in enumerate(turns):
            store().set(TURN_KEY, i)
            times.append(time.time())
            store().set(TURN_TIMES_KEY, times)
            if i > 0:
                agent_state.messages.append(ChatMessageUser(content=turn))
            agent_state = await agent(agent_state)
            replies.append(agent_state.output.completion if agent_state.output else "")
            store().set(REPLIES_KEY, replies)
        state.messages = agent_state.messages
        if agent_state.output is not None:
            state.output = agent_state.output
        return state

    return solve
