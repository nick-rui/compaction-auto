#!/bin/bash
# GPU window on the H100: stop Qwen vLLM, run HF activation jobs, serve gpt-oss-120b on :8001
# for the cross-model check, then restore Qwen vLLM on :8000.
set -x
source ~/cw-venv/bin/activate
cd ~/compaction-auto
tmux kill-session -t vllm; sleep 8
export PYTHONPATH=.
python -m exp.persona.project > exp/persona/project.log 2>&1
python -m exp.persona.capping > exp/persona/capping.log 2>&1
VLLM_USE_DEEP_GEMM=0 vllm serve ~/models/gpt-oss-120b --served-model-name gpt-oss-120b --host 127.0.0.1 --port 8001 \
  --max-model-len 32768 --gpu-memory-utilization 0.92 --enable-prefix-caching > ~/vllm_oss.log 2>&1 &
OSS=$!
until curl -s localhost:8001/v1/models | grep -q gpt-oss; do sleep 5; if ! kill -0 $OSS; then break; fi; done
CA_BASE_URL=http://127.0.0.1:8001/v1 CA_MODEL=gpt-oss-120b python -m exp.persona.xmodel > exp/persona/xmodel.log 2>&1
kill $OSS; sleep 15
tmux new-session -d -s vllm "bash ~/serve.sh > ~/vllm.log 2>&1"
echo WINDOW_DONE
