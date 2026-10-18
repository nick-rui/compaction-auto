#!/bin/bash
# lane B (14 slots): after the summaries run exits -> nosuf + rounds 2-4 (k=0..2), then controls
cd "/Users/nicolema/Library/Application Support/Claude/scratch-workspaces/c92091b7-8bc0-4883-a653-20c265ce0a4f/22f9d993-4553-4d91-9cb4-4d135fca40df/scratch-2026-10-17-eb3ddc/compaction-auto"
export CA_BASE_URLS=http://127.0.0.1:18000/v1,http://127.0.0.1:18001/v1
while kill -0 23409 2>/dev/null; do sleep 5; done
R="exp/ownership/results"
.venv/bin/python -m exp.ownership.run --stage episodes --prefix main --conds claude_nosuf,claude_r2,claude_r3,claude_r4 --k 3 --conc 14 > $R/laneB_1.log 2>&1
.venv/bin/python -m exp.ownership.run --stage episodes --prefix main --conds truncate,full_r4 --k 2 --conc 14 > $R/laneB_2.log 2>&1
echo LANE_B_DONE >> $R/laneB_2.log
