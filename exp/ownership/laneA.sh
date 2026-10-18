#!/bin/bash
# lane A (10 slots): after the full-history run exits -> claude + claude_I (k=0..3), then fill-ins
cd "/Users/nicolema/Library/Application Support/Claude/scratch-workspaces/c92091b7-8bc0-4883-a653-20c265ce0a4f/22f9d993-4553-4d91-9cb4-4d135fca40df/scratch-2026-10-17-eb3ddc/compaction-auto"
export CA_BASE_URLS=http://127.0.0.1:18000/v1,http://127.0.0.1:18001/v1
while kill -0 24123 2>/dev/null; do sleep 5; done
R="exp/ownership/results"
.venv/bin/python -m exp.ownership.run --stage episodes --prefix main --conds claude,claude_I --k 4 --conc 10 > $R/laneA_1.log 2>&1
while kill -0 23409 2>/dev/null; do sleep 5; done
.venv/bin/python -m exp.ownership.run --stage episodes --prefix main --conds claude,claude_I --k 4 --conc 10 > $R/laneA_2.log 2>&1
.venv/bin/python -m exp.ownership.run --stage episodes --prefix main --conds qwen,codex --k 3 --conc 10 > $R/laneA_3.log 2>&1
echo LANE_A_DONE >> $R/laneA_3.log
