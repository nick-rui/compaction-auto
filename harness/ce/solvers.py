"""Use a compaction-controlled real harness as the solver for ANY Inspect eval.

    inspect eval inspect_evals/swe_bench_verified_mini \
        --model openai-api/local/qwen3.8-27b \
        --solver ce/solvers.py@compaction_agent \
        -S harness=codex_cli -S policy=harness_default -S trigger=every_n -S n=4 -S window=120000

Every policy knob from ce/policies.py is a solver parameter (`-S`). Compaction events land
in each sample's store (`ce_events`), so `ce.analysis.compactions_df(log_dir)` works on
these logs too; the eval's own scorer (e.g. SWE-bench tests) measures performance.
"""

from __future__ import annotations

import os

from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.util import store

from ce.agents import make_agent
from ce.policies import build_policy
from ce.solver import converse


@solver
def compaction_agent(
    harness: str = "codex_cli",
    version: str | None = None,
    model_config: str | None = None,
    policy: str = "harness_default",
    trigger: str | None = None,
    window: int | None = None,
    n: int | None = None,
    turns: str | int | None = None,
    max_compactions: int | None = None,
    pre: str | None = None,
    pre_text: str | None = None,
    pre_file: str | None = None,
    post: str | None = None,
    post_template: str | None = None,
    post_file: str | None = None,
    post_prefix: str | None = None,
    post_suffix: str | None = None,
    summarizer: str | None = None,
    system_prompt: str | None = None,
) -> Solver:
    if window is None and os.environ.get("CE_DEFAULT_WINDOW"):
        window = int(os.environ["CE_DEFAULT_WINDOW"])
    pol = build_policy(
        policy, trigger=trigger, window=window, n=n, turns=turns,
        max_compactions=max_compactions, pre=pre, pre_text=pre_text, pre_file=pre_file,
        post=post, post_template=post_template, post_file=post_file,
        post_prefix=post_prefix, post_suffix=post_suffix, summarizer=summarizer,
    )
    agent = make_agent(harness, pol, version=version, model_config=model_config,  # type: ignore[arg-type]
                       system_prompt=system_prompt, cwd=None)
    inner = converse(agent)

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state.metadata = {**(state.metadata or {}), "harness": harness, **pol.describe()}
        store().set("ce_config", {"harness": harness, **pol.describe()})
        return await inner(state, generate)

    return solve
