#!/bin/bash
cd "$(dirname "$0")"
PY=../../.venv/bin/python
$PY rerun.py migration,deploy,email,refund _main main full,truncate,qwen,qwen_notrailer,codex,qwen_shipped continue 16 3 0 > results/main.log 2>&1
$PY decomp.py migration,deploy,email,refund 8 3 continue user orig,R1:gated,R1:actcond,R1:wait,R1:cond,R1:none,R0:gated,R0:none cells > results/decomp_cells.log 2>&1
$PY decomp.py migration,deploy,email,refund 8 3 continue assistant,user_prov,user_notrailer orig,R1:actcond,R1:wait > results/decomp_framing.log 2>&1
echo ALLDONE >> results/main.log
