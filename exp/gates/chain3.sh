#!/bin/bash
cd "$(dirname "$0")"
PY=../../.venv/bin/python
export CA_BASE_URLS=http://127.0.0.1:18001/v1   # main replica is saturated; each experiment runs on one server
$PY probe.py migration,deploy,email,refund 16 2 main _main > results/probe.log 2>&1
$PY recur.py migration,deploy 4 4 continue main > results/recur.log 2>&1
$PY rerun.py migration,deploy,email,refund _main think full,qwen,codex continue 8 2 1 > results/think.log 2>&1
echo ALLDONE >> results/think.log
