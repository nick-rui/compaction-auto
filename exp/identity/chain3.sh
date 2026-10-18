#!/bin/sh
export CA_BASE_URLS=http://127.0.0.1:18000/v1,http://127.0.0.1:18001/v1
while kill -0 11345 2>/dev/null; do sleep 5; done
.venv/bin/python -m exp.identity.onpol --n 4 --conc 22
.venv/bin/python -m exp.identity.run --prefix main --n 3 --k0 0 --frames voiceI,voiceP --probes chain --conc 22
