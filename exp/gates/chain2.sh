#!/bin/bash
cd "$(dirname "$0")"
PY=../../.venv/bin/python
export CA_BASE_URLS=http://127.0.0.1:18000/v1,http://127.0.0.1:18001/v1
until curl -s -m 5 http://127.0.0.1:18001/v1/models | grep -q qwen3; do sleep 15; done
# all decomp cells/framings in one experiment (same servers for every cell)
# main run still occupies 18000 -> run the cells experiment entirely on the second replica
CA_BASE_URLS=http://127.0.0.1:18001/v1 $PY decomp.py migration,deploy,email,refund 8 3 continue user orig,R1:gated,R1:actcond,R1:wait,R1:cond,R1:none,R0:gated,R0:none cells > results/decomp_cells.log 2>&1
until grep -q "^done" results/main.log; do sleep 15; done
$PY decomp.py migration,deploy,email,refund 8 3 continue user,assistant,user_prov,user_notrailer orig,R1:actcond,R1:wait framing > results/decomp_framing.log 2>&1
$PY probe.py migration,deploy,email,refund 16 2 main _main > results/probe.log 2>&1
$PY rerun.py migration,deploy,email,refund _main think full,qwen,codex continue 8 2 1 > results/think.log 2>&1
$PY recur.py migration,deploy 4 4 continue main > results/recur.log 2>&1
echo ALLDONE >> results/recur.log
