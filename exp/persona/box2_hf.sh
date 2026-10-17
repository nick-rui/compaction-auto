#!/bin/bash
# short HF window on box 2: Assistant Axis projections for calibration / edits / instrumental items
source ~/cw-venv/bin/activate
cd ~/compaction-auto
export PYTHONPATH=.
tmux kill-session -t vllm; sleep 10
for f in control edit instrumental; do
  python -m exp.persona.project_items exp/persona/results/${f}_items.jsonl exp/persona/results/proj_${f}.jsonl > exp/persona/proj_$f.log 2>&1
done
tmux new-session -d -s vllm "bash ~/serve.sh > ~/vllm.log 2>&1"
echo HF2_DONE
