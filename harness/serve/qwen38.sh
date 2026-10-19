#!/usr/bin/env bash
# Serve one Qwen3.8-27B replica (bf16, TP=1) on GPU $GPU at port $PORT.
# TP=2 hung in NCCL init on lambda-4xh100, so scale out with one replica per GPU
# behind serve/router.py (sticky by conversation, so prefix caching still works).
set -euo pipefail
cd "$(dirname "$0")/.."
export CUDA_VISIBLE_DEVICES=${GPU:-0}
export PATH="$PWD/.venv-vllm/bin:$PATH"   # JIT kernels need ninja from the venv
exec .venv-vllm/bin/vllm serve "${MODEL_DIR:-$HOME/models/Qwen3.8-27B}" \
  --served-model-name "${SERVED_NAME:-qwen3.8-27b}" \
  --host 127.0.0.1 --port "${PORT:-8000}" \
  --max-model-len "${MAX_LEN:-131072}" \
  --gpu-memory-utilization 0.92 \
  --max-num-seqs "${MAX_SEQS:-64}" \
  --enable-prefix-caching \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 \
  --limit-mm-per-prompt '{"image":0,"video":0}'
