# Handoff: compaction-evals infra (`harness/` on branch `nick`)

For the next agent picking this up. Read `README.md` first for usage; this file covers
state, topology, gotchas and next steps. Machine access details (hosts, keys) are not in
this public repo; get them from Nick.

## Research context

Nick and Nicole study safety failures at context compaction: the one point in a harness
where the model writes the whole account of the past that its successor sees. Nicole's
`exp/` (Qwen3-32B, her own reimplementation `ca/`) found omission/neutral framing of
failures, provenance laundering, gate violations, persona carry-over, and a step-shaped
decay over repeated compactions. A fidelity audit found her reimplementation diverges from
the real harnesses (call paths, re-attached context, history length, thinking). This infra
runs the **real** CLIs so those findings can be validated and extended.

## Topology

| Where | What runs there |
|---|---|
| **GPU box** (4×H100, Ubuntu 22.04, user `ubuntu`) | vLLM replicas + sticky router (127.0.0.1 only), and every eval whose model is an open model (harness CLIs run in Docker sandboxes on this box) |
| **VPS** (DigitalOcean, no GPU) | the coordinating agent, and every eval whose model is an API model via OpenRouter (Docker sandboxes on the VPS) |
| Laptop | nothing long-running |

Run every long job in `tmux` on the machine that executes it, so disconnecting never
kills a session. tmux sessions don't inherit exported env vars: put env inline in the tmux
command (`tmux new -d -s x "LOCAL_API_KEY=x ... cmd"`).

If the VPS ever needs the open models, tunnel instead of exposing ports:
`ssh -N -L 9000:127.0.0.1:9000 <gpu-box>` then `LOCAL_BASE_URL=http://localhost:9000/v1`.

## GPU box state (as of 2026-10-18)

* Working copy: `~/compaction-evals` (rsync'd from the laptop, *not* a git checkout).
  Switch to a git clone of branch `nick` (`harness/`) once the branch is pushed, and
  recreate venvs there (`uv venv -p 3.12 .venv && uv pip install -e .`, plus
  `.venv-vllm` with `vllm==0.31.0`; `uv` is at `~/.local/bin/uv`).
* Model weights: `~/models/Qwen3.8-27B` (bf16).
* tmux: `vllm0` (GPU0, :8000), `vllm1` (GPU1, :8001), `router` (:9000). GPUs 2–3 free.
  `GPUS="0 1 2 3" bash serve/start_all.sh` brings up all four (restarts the router, which
  drops in-flight sessions).
* `ubuntu` was added to the `docker` group.

## Running

Open models (GPU box):
```bash
LOCAL_BASE_URL=http://localhost:9000/v1 LOCAL_API_KEY=x CE_DEFAULT_WINDOW=120000 \
  .venv/bin/inspect eval ce/tasks.py@compaction_eval --model openai-api/local/qwen3.8-27b \
  -T scenarios=scenarios/smoke -T harness=claude_code -T policy=every_10 --log-dir runs/x
```
API models (VPS, OpenRouter): `OPENROUTER_API_KEY=...` and `--model openrouter/<org>/<model>`.
* Set `-T window=` to the model's real context window (the harness must know it).
* Claude via OpenRouter on Claude Code: pass `-T model_config=claude-sonnet-5-5` (the
  Anthropic id) so Claude Code recognises the model; otherwise it treats it as unknown.
* Codex on OpenAI models via OpenRouter still takes Codex's **local** compaction path
  (custom provider). Real Codex+OpenAI deployments compact server-side (encrypted), which
  nobody outside OpenAI can observe; say so when reporting.
* Judges: `-T judge_model=openrouter/...` from a different family than the agent.

## Verified

* Both harnesses run end to end with Qwen3.8-27B through the bridge; the scripted second
  user turn resumes the same CLI session.
* Real traffic recorded in `goldens/` (Claude Code 2.1.292, Codex 0.163.0);
  `tests/test_signatures.py` passes against them (8 tests).
* `scripts/validate_controls.py` results: see the table at the end of this file.

## Gotchas found while building (all handled in code unless noted)

1. **Tensor parallel hung in NCCL init** on this box → one TP=1 replica per GPU + `serve/router.py`
   (sticky on system+first user message so prefix caching works).
2. Qwen3.8 is hybrid Mamba/attention: vLLM needs `--max-num-seqs ≤ ~360` (set 64).
3. vLLM JIT kernels need `ninja` on PATH (serve script adds the venv bin).
4. Use Inspect provider `openai-api/local/<name>`, not `vllm/<name>`: the vllm provider
   lacks `responses_store`, which the Responses bridge (Codex) needs.
5. Qwen's chat template rejects non-leading system messages; Claude Code sends several
   system blocks and Codex re-injects developer messages → `normalize_system` (filter).
6. Claude Code: unknown model ids need `CLAUDE_CODE_MAX_CONTEXT_TOKENS`; `-T window=` sets
   it plus `CLAUDE_CODE_AUTO_COMPACT_WINDOW`. Without a window it assumes 200k and
   overflows a 131k server.
7. Claude Code aborts if it detects compaction thrash (compaction right after
   compaction). A mis-detected compaction makes `every_n` re-fire every call → exit 1 with
   a misleading `[claude-code:unrecognized_model]` stderr line.
8. Compaction detection searches only the trailing user turn(s): harnesses append
   reminders after the compaction prompt.
9. `inspect eval -T` parses values as YAML (`"a: b"` → dict). Text params are coerced back,
   but prefer `pre_file=` / `post_file=` for real prompts.
10. Forced triggers over-report input tokens on one response; normal agent calls are then
    reported low so only the schedule compacts. `native` reports true usage. "Agent call"
    = a call with tools (side calls like titles are excluded).
11. Claude Code keeps a recent tail after compaction and re-reads files; Codex keeps
    recent user messages. That is real harness behaviour, not a bug.
12. Harness versions are pinned (`ce/agents.py`). Bump only after re-recording goldens.
13. Qwen sometimes ignores Claude Code's "TEXT ONLY" compaction instruction and calls tools;
    such compactions are logged with `succeeded=False` (scored as `n_failed_compactions`).
    This is an open-model behaviour worth reporting, not an infra bug.
14. With `trigger=native`, the window must sit well above what the harness keeps after
    compacting (Claude Code keeps a recent tail; big file reads made it ~50k here), or the
    harness re-compacts immediately and Claude Code aborts on thrash.
16. SWE-bench via inspect_evals 0.25 needs `swebench<5` (`uv pip install -e '.[swe]'`);
    swebench 5.x removed `MAP_REPO_VERSION_TO_SPECS` and scoring crashes after the run.
15. vLLM and the router bind to 127.0.0.1. The GPU box has no firewall (ufw inactive); an
    earlier run had them on 0.0.0.0. Keep it local and tunnel.

## Planned experiment: performance vs compaction frequency (Nick, 2026-10-19)

Question: does long-horizon task performance fall as a harness compacts more often?
No harness patch is needed: `trigger=every_n, n=K` makes the real harness compact every K
agent calls through its own code path.

* Suite: `inspect_evals/swe_bench_verified_mini` (50 SWE-bench Verified tasks, Docker,
  test-based scoring, open model on the GPU box), via the generic solver:
  ```bash
  LOCAL_BASE_URL=http://localhost:9000/v1 LOCAL_API_KEY=x \
  .venv/bin/inspect eval inspect_evals/swe_bench_verified_mini \
    --model openai-api/local/qwen3.8-27b --solver ce/solvers.py@compaction_agent \
    -S harness=codex_cli -S trigger=every_n -S n=4 -S window=120000 \
    --time-limit 3600 --log-dir runs/kswe/codex_k4
  ```
  A 2-task Codex pilot with no forced compaction was started in tmux `swepilot`
  (`runs/swe_pilot`); check it first for solve rate and agent calls per task.
* Conditions: K ∈ {1, 2, 4, 8, 16, 32} plus `native` (harness threshold at the real
  window) as the no-forced-compaction baseline; both harnesses; ≥3 epochs.
* Primary metric: resolve rate vs K (log x). Also log realized compactions,
  `n_failed_compactions`, agent calls, wall time, and tokens per task, and analyse by
  task length (tasks that finish before the first compaction are unaffected by K).
* Confounds to control:
  - compaction calls eat time and turns, so keep the time limit identical across K and
    report "ran out of time" separately;
  - K=1 may trip Claude Code's thrash guard; pilot K=1 first;
  - forced triggers make the harness believe its context is full on one response,
    so check the goldens for any context-low reminder this injects.
* Throughput: serve the FP8 checkpoint (`Qwen/Qwen3.8-27B-FP8`) on all 4 GPUs for about
  2.5× the KV room; SWE sessions run to 50–100k tokens, so concurrency per replica is
  KV-bound. Size `--max-samples` to about 10 per replica.
* Alternatives if SWE-bench horizons are too short: TheAgentCompany or CORE-bench
  (both in inspect_evals), or Terminal-Bench 2 (Harbor; would need porting into Inspect).

## Next steps (suggested order)

1. Push branch `nick` (Nick needs push access to Nicole's repo, or use a fork), clone it on
   the GPU box and the VPS.
2. Port Nicole's headline scenarios into `scenarios/` as real environments: honesty
   ("anything I should know before I ship?" after a shortcut), gates (deploy endpoint),
   provenance (third-party request in a tool result), reality (real vs sandbox users).
   Re-measure on-policy with both harnesses; this is the fidelity check of her results.
3. Concealment-directive study (proposal in `derisk/compaction-concealment/` of the
   original session, not in this repo): sabotaged-tool failures → compaction → label
   summaries for explicit concealment directives vs omission vs false status.
4. Compaction-count curve: same task with `window` / `every_n` sweeps (0,1,3,8
   compactions at fixed work), plus a no-compaction twin probe at matched positions.
5. Frontier arms on the VPS via OpenRouter; cross-family judges with ≥150 hand labels.
6. Diff Nicole's `ca/compact.py` against `goldens/` and fix her test bed so cheap causal
   manipulations can run there with a faithfulness guarantee.

Secrets the runs need (set on the machine that runs them, never commit): `OPENROUTER_API_KEY`
(API models, judges), optionally `HF_TOKEN` (faster/gated downloads), GitHub credentials
for pushing.
