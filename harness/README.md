# compaction-evals

**Agents: start with `HANDOFF.md`** (project workstreams + operating rules).

Run real agent harnesses (Claude Code, Codex CLI) on scripted tasks and control everything
about compaction: the pre-compaction prompt, the post-compaction message, and when
compaction fires. Built on [Inspect](https://inspect.aisi.org.uk/) +
[inspect_swe](https://meridianlabs-ai.github.io/inspect_swe/): the CLIs run unmodified
inside Docker sandboxes, and every model call they make goes through the Inspect agent
bridge, where `ce/filter.py` applies the experiment's compaction policy and logs it.

```
 harness CLI (claude / codex) in sandbox
        │  Anthropic Messages / OpenAI Responses API
        ▼
 Inspect agent bridge ──► ce.filter (classify call; rewrite pre/post; trigger; log)
        │
        ▼
 Inspect model  ──► serve/router.py (sticky) ──► vLLM replicas (one per GPU)
```

## What you can control

| Knob | How it works | Task params (`-T`) |
|---|---|---|
| **Pre-compaction prompt** | The harness builds its own compaction request; the filter finds the prompt message and replaces / appends / prepends text | `pre=replace\|append\|prepend`, `pre_text=...` or `pre_file=path` |
| **Post-compaction message** | Every call after a compaction contains the harness's wrapper + summary; the filter splits it and re-renders it the same way on every call | `post=template\|wrap`, `post_template="...{summary}..."` or `post_file`, `post_prefix`, `post_suffix` |
| **Summary edits** | Text planted inside the real post-compaction summary (or any `PostPrompt.summary_transform(summary) -> str` in Python) | `summary_append=...`, `summary_prepend=...` |
| **When to compact** | The harness's own auto-compact logic decides; the filter controls the *reported* context usage. `native` = harness threshold from `window`; `every_n` / `at_turns` force a compaction after N agent calls / at given calls; `at_user_turns` compacts at the boundary before the listed scripted user turns (0-based); `never` keeps usage low | `trigger=native\|every_n\|at_turns\|at_user_turns\|never`, `n=`, `turns=3,8`, `user_turns=1,2`, `max_compactions=`, `window=` |
| **Context window** | Claude Code: `CLAUDE_CODE_AUTO_COMPACT_WINDOW`; Codex: `model_context_window` + `model_auto_compact_token_limit` (0.9×) | `window=` (or env `CE_DEFAULT_WINDOW`) |
| **Summarizer model** | Compaction calls routed to a different Inspect model | `summarizer=openai-api/local/other-model` |
| **Anchors** | Scenario `anchors:` text is written to `CLAUDE.md` and `AGENTS.md` (files the harnesses reload) | scenario YAML |
| **Harness version** | Pinned per run | `version=2.1.292` |

Presets (`policy=`): `harness_default`, `never`, `every_5`, `every_10`, `every_20`,
`honest_pre`, `neutral_post` (see `ce/policies.py`). Explicit `-T` params override presets.

## Running

On the GPU box (`lambda-4xh100`, project in `~/compaction-evals`):

```bash
# serve: one Qwen3.8-27B replica per GPU + sticky router on :9000 (GPUS="0 1 2 3" for all four)
GPUS="0 1" bash serve/start_all.sh

# (tmux sessions don't inherit exports: put these inline in any tmux command)
export LOCAL_BASE_URL=http://localhost:9000/v1 LOCAL_API_KEY=x CE_DEFAULT_WINDOW=120000
.venv/bin/inspect eval ce/tasks.py@compaction_eval --model openai-api/local/qwen3.8-27b \
    -T scenarios=scenarios/smoke -T harness=claude_code -T policy=every_5 -T max_compactions=3 \
    --log-dir runs/smoke

.venv/bin/python scripts/inspect_log.py runs/smoke/<log>.eval     # readable trace
.venv/bin/python scripts/run_grid.py configs/example_grid.yaml      # grids
.venv/bin/python scripts/validate_controls.py run                   # end-to-end check of every control
.venv/bin/python -m pytest -q tests                                 # detectors vs recorded goldens
```

Recorded goldens: Claude Code 2.1.292 and Codex CLI 0.163.0 (`goldens/`). They are taken
from what the model received, i.e. after `normalize_system`; prompt and post-message text
is untouched by it.

Use `openai-api/local/<served-name>` (not `vllm/...`): Inspect's vLLM provider lacks
attributes the Responses-API bridge (Codex) needs. Frontier arms just use another model,
e.g. `--model anthropic/claude-sonnet-5-5` (needs `ANTHROPIC_API_KEY` on the box).

## Scenarios

YAML files in `scenarios/` (format documented in `ce/scenario.py`): workspace files,
generated padding files (to build up context), mocked external services (`env/mocksvc.py`
logs every request to `/var/log/ce/requests.jsonl`), anchors, scripted user turns, and
checks. Checks are deterministic (`request` (optionally scoped to one scripted `turn:`), `file`, `reply_regex`, `command`); `retain:` regexes are checked against everything the successor sees after each compaction; optional
`judge:` items are scored by `-T judge_model=<model>` (use a different family than the agent).

## Outputs

Each sample's store holds `ce_events`: every compaction (index, agent-call number, the
prompt actually sent, the summary, stop reason) and every post-compaction message (as
placed), plus forced triggers. `ce.analysis.samples_df(dir)` / `compactions_df(dir)` turn
a log directory into DataFrames. Inspect ModelEvents show exactly what the model saw.

## Fidelity notes (read before claiming "real deployment")

* **Harness logic is real**: the CLI decides what to keep, builds the compaction request,
  rebuilds context (Claude Code keeps a recent tail, re-reads files, reloads CLAUDE.md;
  Codex keeps recent user messages, re-injects AGENTS.md). Nothing is reimplemented.
* **Goldens**: `scripts/capture_goldens.py` records the real compaction prompt and post
  message per harness version into `goldens/`; `tests/test_signatures.py` checks the
  detectors against them. Re-capture when bumping a harness version.
* **Open-model adaptations** (logged, on by default): leading system blocks are merged and
  mid-conversation system messages become `<system-message>` user turns, because Qwen's
  chat template rejects them (`normalize_system`). Claude Code presents the served model's
  name as its identity ("You are powered by the model qwen3.8-27b").
* **Forced triggers** work by over-reporting input tokens on one response; the harness then
  compacts through its normal path. `native` mode reports true usage.
* Codex here uses a custom provider name, so it takes the **local** compaction path (the
  prompt in `codex-rs/prompts/templates/compact/`). Codex on OpenAI models compacts
  server-side (encrypted), which this setup cannot observe.
* Sandboxes have no network; the agent reaches the model only through the bridge.
