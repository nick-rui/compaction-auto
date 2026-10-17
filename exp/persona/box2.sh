#!/bin/bash
# Mechanistic jobs on the second H100 (dedicated; no vLLM here).
source ~/cw-venv/bin/activate
cd ~/compaction-auto
export PYTHONPATH=.
CAP_CUTS=selfharm:29 CAP_N=12,2,8 CAP_OUT=capping2.jsonl python -m exp.persona.capping > exp/persona/capping2.log 2>&1
CAP_CUTS=selfharm:28,delusion:18 CAP_N=8,2,4 CAP_OUT=capping2.jsonl python -m exp.persona.capping >> exp/persona/capping2.log 2>&1
echo BOX2_DONE
