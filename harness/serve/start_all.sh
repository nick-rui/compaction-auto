#!/usr/bin/env bash
# Start one Qwen3.8-27B replica per listed GPU and the sticky router on :9000.
#   GPUS="0 1 2 3" bash serve/start_all.sh        (default: 0 1)
# Restarting the router drops in-flight agent sessions; don't run this mid-eval.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
GPUS=${GPUS:-"0 1"}
backends=()
for g in $GPUS; do
  port=$((8000 + g))
  tmux kill-session -t "vllm$g" 2>/dev/null || true
  tmux new-session -d -s "vllm$g" "GPU=$g PORT=$port bash serve/qwen38.sh 2>&1 | tee logs/vllm_gpu$g.log"
  backends+=("http://localhost:$port")
done
for b in "${backends[@]}"; do
  until curl -s -m 2 "$b/v1/models" >/dev/null; do sleep 5; done
  echo "up: $b"
done
tmux kill-session -t router 2>/dev/null || true
tmux new-session -d -s router ".venv/bin/python serve/router.py --port 9000 --backends ${backends[*]} 2>&1 | tee logs/router.log"
echo "router on :9000 -> ${backends[*]}"
