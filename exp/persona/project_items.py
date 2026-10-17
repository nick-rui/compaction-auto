"""Generic Assistant Axis projection for any {id, messages, response[, tools], ...} jsonl.

  python -m exp.persona.project_items in.jsonl out.jsonl
Used to ask whether compaction-induced *instrumental* misbehavior (gated actions, laundered
injections, undisclosed mistakes) moves the model off the Assistant Axis at all.
"""

import json
import sys

from ca.axis import Axis


def main(src, dst):
    ax = Axis()
    with open(dst, "w") as out:
        for item in map(json.loads, open(src)):
            p, n, plen = ax.project(item["messages"], item["response"], tools=item.get("tools"))
            meta = {k: v for k, v in item.items() if k not in ("messages", "response", "tools")}
            out.write(json.dumps({**meta, "proj": p, "n_tok": n, "ctx_tok": plen}) + "\n")
            out.flush()


if __name__ == "__main__":
    main(*sys.argv[1:3])
