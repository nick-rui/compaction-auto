#!/bin/sh
# runs after the base k=0..2 pass: voice intervention (n=33) then extend key cells to k=3..5 (n=66)
export CA_BASE_URLS=http://127.0.0.1:18000/v1,http://127.0.0.1:18001/v1
while kill -0 9260 2>/dev/null; do sleep 5; done
.venv/bin/python -m exp.identity.run --prefix main --n 3 --k0 0 --frames voiceI,voiceP --probes resp,ask,eval --conc 24
.venv/bin/python -m exp.identity.run --prefix main --n 3 --k0 3 --frames self,other,neutral,voiceI,voiceP,qwen,full --probes resp,ask,eval --conc 24
