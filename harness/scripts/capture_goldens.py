"""Record a harness's real compaction traffic as golden files.

From an eval log run with `policy=harness_default` pre/post (so nothing is rewritten),
save for the first compaction:
  goldens/<harness>/<version>/compaction_request.json   full input of the compaction call
  goldens/<harness>/<version>/compaction_prompt.txt     the pre-compaction prompt message
  goldens/<harness>/<version>/post_message.txt          the first post-compaction message
  goldens/<harness>/<version>/post_context.json         full input of the successor's first call
These pin what "faithful" means for each harness version: tests/test_signatures.py checks
the detectors against them, and any test-bed reimplementation can be diffed against them.

    python scripts/capture_goldens.py LOG --harness claude_code --version 2.1.292
"""

import argparse
import json
from pathlib import Path

from inspect_ai.log import read_eval_log

from ce.signatures import SIGNATURES, compaction_prompt_index, message_text, post_message_indices


def dump_messages(msgs) -> list[dict]:
    return [{"role": m.role, "text": message_text(m)} for m in msgs]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--harness", required=True, choices=sorted(SIGNATURES))
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", default="goldens")
    a = ap.parse_args()
    sig = SIGNATURES[a.harness]
    log = read_eval_log(a.log, resolve_attachments=True)
    out = Path(a.out) / a.harness / a.version
    out.mkdir(parents=True, exist_ok=True)
    for s in log.samples or []:
        models = [e for e in s.events if e.event == "model"]
        comp = next((e for e in models if compaction_prompt_index(e.input, sig) is not None), None)
        if comp is None:
            continue
        i = compaction_prompt_index(comp.input, sig)
        (out / "compaction_request.json").write_text(json.dumps(dump_messages(comp.input), indent=1))
        (out / "compaction_prompt.txt").write_text(message_text(comp.input[i]))
        post = next((e for e in models[models.index(comp) + 1 :] if post_message_indices(e.input, sig)), None)
        if post is not None:
            j = post_message_indices(post.input, sig)[0]
            (out / "post_message.txt").write_text(message_text(post.input[j]))
            (out / "post_context.json").write_text(json.dumps(dump_messages(post.input), indent=1))
        print(f"wrote {out} from sample {s.id}")
        return
    raise SystemExit("no compaction found in log")


if __name__ == "__main__":
    main()
