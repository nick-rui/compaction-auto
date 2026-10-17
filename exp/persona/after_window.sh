#!/bin/bash
# behavioral follow-ups once Qwen vLLM is back (run locally)
export PYTHONPATH=.
PY=.venv/bin/python
until grep -q "selfharm 160" exp/persona/gen2.log 2>/dev/null; do sleep 30; done
$PY -m exp.persona.judge_dirs gen2 gen2dirs
for c in delusion selfharm; do $PY -m exp.persona.judge_file exp/persona/results/gen2_$c.jsonl exp/persona/results/gen2_judged_$c.jsonl; done
$PY -m exp.persona.framing
$PY -m exp.persona.judge_dirs framing framingdirs
$PY -m exp.persona.control
echo AFTER_DONE
