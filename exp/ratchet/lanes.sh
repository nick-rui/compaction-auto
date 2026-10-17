#!/bin/bash
# Follow-up queue: each lane waits for its main run, then runs controls sequentially.
cd "$(dirname "$0")/../.."
export PYTHONPATH=.
PY=.venv/bin/python
lane_L() {
  while pgrep -f "run_laundering --cond qwen --scn" >/dev/null; do sleep 30; done
  RATCHET_CONC=14 $PY -m exp.ratchet.run_laundering --cond full --scn memleak flaky --n 10 --K 5 > exp/ratchet/logs/laund_full.log 2>&1
  RATCHET_CONC=14 $PY -m exp.ratchet.run_laundering --cond qwen_fixed qwen_hp --scn memleak flaky --n 15 --K 5 > exp/ratchet/logs/laund_fixed_hp.log 2>&1
  RATCHET_CONC=14 $PY -m exp.ratchet.run_laundering --cond codex --scn memleak flaky --n 12 --K 5 > exp/ratchet/logs/laund_codex.log 2>&1
}
lane_F() {
  while pgrep -f "run_feedback --dyn qwen full --seed adv mun --n 30" >/dev/null; do sleep 30; done
  RATCHET_CONC=16 $PY -m exp.ratchet.run_feedback --dyn qwen_fixed qwen_hp --seed adv mun --n 20 --T 6 > exp/ratchet/logs/fb_fixed_hp.log 2>&1
  RATCHET_CONC=16 $PY -m exp.ratchet.run_feedback --dyn full qwen --seed adv mun --n 8 --T 6 --think > exp/ratchet/logs/fb_think.log 2>&1
  RATCHET_CONC=16 $PY -m exp.ratchet.run_feedback --dyn pure --seed adv mun --n 15 --T 6 > exp/ratchet/logs/fb_pure.log 2>&1
  RATCHET_CONC=16 $PY -m exp.ratchet.run_feedback --dyn full qwen --seed none --n 15 --T 6 > exp/ratchet/logs/fb_none.log 2>&1
}
lane_L &
lane_F &
wait
