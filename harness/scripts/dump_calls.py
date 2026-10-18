"""Dump raw model calls from a log (for updating harness signatures / goldens).

    python scripts/dump_calls.py LOG --calls 6,7 [--sample ID] [--chars 8000]
Prints each selected call's full input (role + text) and output.
"""

import argparse

from inspect_ai.log import read_eval_log

ap = argparse.ArgumentParser()
ap.add_argument("log")
ap.add_argument("--calls", required=True, help="1-based model-call indices, comma separated")
ap.add_argument("--sample", default=None)
ap.add_argument("--chars", type=int, default=8000)
a = ap.parse_args()
want = {int(x) for x in a.calls.split(",")}
log = read_eval_log(a.log, resolve_attachments=True)
for s in log.samples or []:
    if a.sample and str(s.id) != a.sample:
        continue
    models = [e for e in s.events if e.event == "model"]
    for i, e in enumerate(models, 1):
        if i not in want:
            continue
        print(f"\n################ call {i}: {len(e.input)} messages, {len(e.tools)} tools")
        for j, m in enumerate(e.input):
            print(f"--- [{j}] {m.role} ({len(m.text)} chars)\n{m.text[: a.chars]}")
        print(f"--- OUTPUT\n{(e.output.completion or '')[: a.chars]}")
