"""Inspect task entry point for every compaction experiment.

    inspect eval ce/tasks.py@compaction_eval \
        --model vllm/qwen3.8-27b \
        -T scenarios=scenarios/smoke -T harness=claude_code \
        -T policy=every_10 -T window=64000

All policy knobs from ce/policies.py are task parameters, so a grid is just several
`-T` combinations (see scripts/run_grid.py).
"""

from __future__ import annotations

import os
from pathlib import Path

from inspect_ai import Task, task

from ce.agents import make_agent
from ce.policies import build_policy
from ce.scenario import load_scenarios
from ce.scorers import checks, judged
from ce.solver import converse

ROOT = Path(__file__).resolve().parent.parent
ENV_DIR = ROOT / "env"


@task
def compaction_eval(
    scenarios: str = "scenarios/smoke",
    harness: str = "claude_code",
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
    judge_model: str | None = None,
    system_prompt: str | None = None,
    debug: bool = False,
) -> Task:
    # the harness must be told the real context window of the served model, or it will
    # overflow it before compacting; CE_DEFAULT_WINDOW sets this for a deployment
    if window is None and os.environ.get("CE_DEFAULT_WINDOW"):
        window = int(os.environ["CE_DEFAULT_WINDOW"])
    pol = build_policy(
        policy, trigger=trigger, window=window, n=n, turns=turns,
        max_compactions=max_compactions, pre=pre, pre_text=pre_text, pre_file=pre_file,
        post=post, post_template=post_template, post_file=post_file,
        post_prefix=post_prefix, post_suffix=post_suffix, summarizer=summarizer,
    )
    agent = make_agent(harness, pol, version=version, model_config=model_config,
                       system_prompt=system_prompt, debug=debug)  # type: ignore[arg-type]
    # inspect runs tasks from the task file's directory; resolve paths from the repo root
    paths = [p if Path(p).is_absolute() else str(ROOT / p) for p in scenarios.split(",")]
    samples = load_scenarios(paths)
    for s in samples:
        s.metadata = {**(s.metadata or {}), "harness": harness, **pol.describe()}
    return Task(
        dataset=samples,
        solver=converse(agent),
        scorer=[checks(), judged(judge_model)],
        sandbox=("docker", str(ENV_DIR / "compose.yaml")),
        metadata={"harness": harness, **pol.describe()},
    )
