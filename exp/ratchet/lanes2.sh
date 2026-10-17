#!/bin/bash
# New experiments on the second replica only (main server is saturated).
cd "$(dirname "$0")/../.."
export PYTHONPATH=. CA_BASE_URLS=http://127.0.0.1:18001/v1
PY=.venv/bin/python
until [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:18001/v1/models)" = "200" ]; do sleep 15; done
echo "replica up $(date)"
laneA() {
  RATCHET_CONC=16 $PY -m exp.ratchet.run_feedback --dyn qwen_fixed qwen_hp --seed adv mun --n 20 --T 5 > exp/ratchet/logs/fb_fixed_hp.log 2>&1
  RATCHET_CONC=16 $PY -m exp.ratchet.run_feedback --dyn full qwen --seed adv mun --n 8 --T 5 --think > exp/ratchet/logs/fb_think.log 2>&1
}
laneB() {
  RATCHET_CONC=12 $PY -m exp.ratchet.run_laundering --cond qwen_fixed qwen_hp --scn memleak flaky --n 12 --K 4 > exp/ratchet/logs/laund_fixed_hp.log 2>&1
  RATCHET_CONC=12 $PY -m exp.ratchet.run_feedback --dyn pure --seed adv mun --n 12 --T 5 > exp/ratchet/logs/fb_pure.log 2>&1
  RATCHET_CONC=12 $PY -m exp.ratchet.run_feedback --dyn full qwen --seed none --n 12 --T 5 > exp/ratchet/logs/fb_none.log 2>&1
}
laneA & laneB & wait
echo "all done $(date)"
