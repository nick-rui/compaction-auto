"""Real harnesses (via inspect_swe) with a CompactionPolicy attached."""

from __future__ import annotations

from typing import Literal

from inspect_ai.agent import Agent
from inspect_swe import claude_code, codex_cli

from .filter import compaction_filter
from .policy import CompactionPolicy

Harness = Literal["claude_code", "codex_cli"]

# Pinned harness versions = the versions goldens/ were recorded from. Compaction behaviour
# and prompt text change between releases; to bump, run a smoke eval with the new version,
# re-run scripts/capture_goldens.py, and make tests/ pass before using it in experiments.
DEFAULT_VERSIONS: dict[str, str] = {"claude_code": "2.1.292", "codex_cli": "0.163.0"}


def native_trigger_settings(harness: Harness, policy: CompactionPolicy) -> tuple[dict, dict]:
    """(env, config_overrides) that set the harness's own auto-compact threshold."""
    env: dict[str, str] = {}
    cfg: dict[str, str] = {}
    w = policy.trigger.window_tokens
    if w is not None:
        if harness == "claude_code":
            # for model ids Claude Code doesn't recognise (open models), the window must be
            # declared via CLAUDE_CODE_MAX_CONTEXT_TOKENS; AUTO_COMPACT_WINDOW caps it further
            env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(w)
            env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(w)
        else:
            cfg["model_context_window"] = str(w)
            cfg["model_auto_compact_token_limit"] = str(int(w * 0.9))
    return env, cfg


def make_agent(
    harness: Harness,
    policy: CompactionPolicy | None = None,
    *,
    version: str | None = None,
    model: str | None = None,
    model_config: str | None = None,
    system_prompt: str | None = None,
    env: dict[str, str] | None = None,
    config_overrides: dict[str, str] | None = None,
    cwd: str | None = "/workspace",
    debug: bool = False,
) -> Agent:
    policy = policy or CompactionPolicy()
    nenv, ncfg = native_trigger_settings(harness, policy)
    filt = compaction_filter(policy, harness)
    version = version or DEFAULT_VERSIONS[harness]
    if harness == "claude_code":
        return claude_code(
            system_prompt=system_prompt,
            model=model,
            # identity Claude Code presents ("You are powered by ..."); for Claude models
            # reached through OpenRouter pass the Anthropic id (e.g. claude-sonnet-5-5) so
            # Claude Code recognises it and uses the right window / features
            model_config=model_config,
            filter=filt,
            cwd=cwd,
            version=version,
            env={**nenv, **(env or {}), **policy.extra_env},
            disallowed_tools=["WebSearch", "WebFetch"],
            debug=debug,
        )
    if harness == "codex_cli":
        return codex_cli(
            system_prompt=system_prompt,
            model=model,
            model_config=model_config,
            filter=filt,
            cwd=cwd,
            version=version,
            env={**(env or {}), **policy.extra_env} or None,
            config_overrides={**ncfg, **(config_overrides or {}), **policy.extra_config},
            web_search="disabled",
            debug=debug,
        )
    raise ValueError(f"unknown harness {harness}")
