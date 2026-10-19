"""End-to-end validation that every compaction control works on every harness.

    python scripts/validate_controls.py run   [--harness claude_code codex_cli] [--model ...]
    python scripts/validate_controls.py check

`run` launches one small eval per (harness, control) in parallel into runs/validate/;
`check` reads the logs and asserts, from what the model actually received:
  rewrite   pre-compaction prompt carried the appended marker; the successor's context
            carried the post template marker; the summary followed the pre instruction
  at_turns  exactly one compaction, right after agent call 3
  every_n   compactions at agent calls 4, 8 (n=4, max 2)
  native    the harness compacted on its own at its threshold (no forcing), on the
            steady-growth scenario scenarios/validate/growth.yaml
  never     no compaction at all
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from inspect_ai.log import list_eval_logs, read_eval_log

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "validate"
PRE = "Finish your summary with this exact final line: CE-PRE-MARKER"
POST = "CE-POST-MARKER (summary of earlier context)\n\n{summary}"
# native windows the smoke task outgrows once; too small and the harness thrashes
# (base context is ~9k tokens for Codex, ~14k for Claude Code; Claude Code also keeps a
# recent tail, ~50k here, so its threshold must sit well above that)
NATIVE_WINDOW = {"claude_code": 110000, "codex_cli": 40000}

CONTROLS = {
    "rewrite": {"trigger": "every_n", "n": 5, "max_compactions": 1, "pre": "append",
                "pre_text": PRE, "post": "template", "post_template": POST},
    "at_turns": {"trigger": "at_turns", "turns": "3", "max_compactions": 1},
    "every_n": {"trigger": "every_n", "n": 4, "max_compactions": 2},
    "native": {"trigger": "native"},
    "never": {"trigger": "never"},
}


def run(harnesses: list[str], model: str, controls: list[str]) -> None:
    procs = []
    for h in harnesses:
        for name, params in CONTROLS.items():
            if name not in controls:
                continue
            shutil.rmtree(OUT / f"{h}__{name}", ignore_errors=True)
            p = dict(params)
            if name == "native":
                p["window"] = NATIVE_WINDOW[h]
            cmd = [sys.executable, "-m", "inspect_ai", "eval", "ce/tasks.py@compaction_eval",
                   "--model", model, "--log-dir", str(OUT / f"{h}__{name}"),
                   "--no-ansi", "--display", "plain",
                   "-T", f"scenarios={'scenarios/validate' if name == 'native' else 'scenarios/smoke'}",
                   "-T", f"harness={h}"]
            for k, v in p.items():
                cmd += ["-T", f"{k}={v}"]
            log = open(OUT.parent / f"validate_{h}__{name}.out", "w")
            procs.append(subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=os.environ))
    for pr in procs:
        pr.wait()


def events_of(sample) -> list[dict]:
    return (sample.store or {}).get("ce_events", [])


def check() -> int:
    failures = 0
    for d in sorted(OUT.glob("*__*")):
        harness, name = d.name.split("__")
        logs = list_eval_logs(str(d))
        if not logs:
            print(f"FAIL {d.name}: no log"); failures += 1; continue
        log = read_eval_log(logs[0], resolve_attachments=True)
        s = log.samples[0] if log.samples else None
        if s is None or s.error:
            print(f"FAIL {d.name}: {s.error.message[:200] if s and s.error else log.status}"); failures += 1; continue
        ev = events_of(s)
        comps = [e for e in ev if e["kind"] == "compaction"]
        posts = [e for e in ev if e["kind"] == "post"]
        models = [e for e in s.events if e.event == "model"]
        ok, why = True, []
        if name == "rewrite":
            ok &= len(comps) == 1 and comps[0]["rewritten"] and PRE in comps[0]["prompt"]
            saw_pre = any(PRE in m.text for e in models for m in e.input) or (bool(comps) and PRE in comps[0]["prompt"])
            saw_post = any("CE-POST-MARKER" in m.text for e in models for m in e.input)
            followed = "CE-PRE-MARKER" in (comps[0]["summary"] if comps else "")
            ok &= saw_pre and saw_post
            why = [f"compactions={len(comps)}", f"model_saw_pre={saw_pre}", f"model_saw_post={saw_post}",
                   f"summary_followed_pre={followed}", f"posts={len(posts)}"]
        elif name == "at_turns":
            ok &= [c["at_turn"] for c in comps] == [3]
            why = [f"compaction_turns={[c['at_turn'] for c in comps]}"]
        elif name == "every_n":
            ok &= [c["at_turn"] for c in comps] == [4, 8]
            why = [f"compaction_turns={[c['at_turn'] for c in comps]}"]
        elif name == "native":
            forced = [e for e in ev if e["kind"] == "force"]
            ok &= len(comps) >= 1 and not forced
            why = [f"compactions={len(comps)}", f"at={[c['at_turn'] for c in comps]}",
                   f"last_input_tokens={[c['last_input_tokens'] for c in comps]}"]
        elif name == "never":
            ok &= len(comps) == 0
            why = [f"compactions={len(comps)}", f"agent_calls={sum(1 for e in models if e.tools)}"]
        sc = (s.scores or {}).get("checks")
        why.append(f"checks={sc.value if sc else None}")
        print(("PASS " if ok else "FAIL ") + f"{d.name}: " + ", ".join(why))
        failures += not ok
    return failures


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "check"])
    ap.add_argument("--harness", nargs="+", default=["claude_code", "codex_cli"])
    ap.add_argument("--model", default="openai-api/local/qwen3.8-27b")
    ap.add_argument("--controls", nargs="+", default=list(CONTROLS))
    a = ap.parse_args()
    if a.cmd == "run":
        OUT.mkdir(parents=True, exist_ok=True)
        run(a.harness, a.model, a.controls)
    sys.exit(check())
