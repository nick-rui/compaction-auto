#!/bin/bash
# lane C: think=True replication (after lane B finishes): probe first (cheap), then harm
cd "/Users/nicolema/Library/Application Support/Claude/scratch-workspaces/c92091b7-8bc0-4883-a653-20c265ce0a4f/22f9d993-4553-4d91-9cb4-4d135fca40df/scratch-2026-10-17-eb3ddc/compaction-auto"
export CA_BASE_URLS=http://127.0.0.1:18000/v1,http://127.0.0.1:18001/v1
R="exp/ownership/results"
until grep -q LANE_B_DONE $R/laneB_2.log 2>/dev/null; do sleep 10; done
.venv/bin/python -m exp.ownership.run --stage episodes --prefix think --think --conds full,claude --probes probe --k 3 --conc 14 > $R/laneC_1.log 2>&1
.venv/bin/python -m exp.ownership.run --stage episodes --prefix think --think --conds full,claude --probes harm --k 2 --conc 14 > $R/laneC_2.log 2>&1
echo LANE_C_DONE >> $R/laneC_2.log
