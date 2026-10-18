"""Print a readable trace of one sample's model traffic, compaction events and scores.

    python scripts/inspect_log.py runs/smoke/<file>.eval [--sample ID] [--full]
"""

import argparse

from inspect_ai.log import read_eval_log


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--sample", default=None)
    ap.add_argument("--full", action="store_true", help="print full compaction prompts/summaries")
    a = ap.parse_args()
    log = read_eval_log(a.log, resolve_attachments=True)
    print(f"status={log.status} error={log.error.message[:300] if log.error else None}")
    for s in log.samples or []:
        if a.sample and str(s.id) != a.sample:
            continue
        print(f"\n=== sample {s.id}  error={s.error.message[:300] if s.error else None}")
        n = 0
        for e in s.events:
            if e.event == "model":
                n += 1
                u = e.output.usage
                calls = [t.function for t in (e.output.message.tool_calls or [])]
                last = e.input[-1].text if e.input else ""
                print(
                    f"[{n:3d}] model in_msgs={len(e.input):3d} tools={len(e.tools):2d} "
                    f"in_tok={u.input_tokens if u else None} calls={calls} err={str(e.error)[:120] if e.error else ''}"
                )
                print(f"      last_input: {last[:160]!r}")
                print(f"      output:     {(e.output.completion or '')[:160]!r}")
            elif e.event == "info" and getattr(e, "source", None) == "ce":
                d = dict(e.data) if isinstance(e.data, dict) else {"data": e.data}
                print(f"      >>> ce {d.get('kind')}: " + ", ".join(
                    f"{k}={str(v)[:80]!r}" for k, v in d.items() if k not in ("kind", "harness", "policy")))
        st = s.store or {}
        for ev in st.get("ce_events", []):
            if ev["kind"] == "compaction":
                print(f"\n--- compaction #{ev['index']} at agent call {ev['at_turn']} (rewritten={ev['rewritten']})")
                print("PROMPT:", ev["prompt"] if a.full else ev["prompt"][:600])
                print("SUMMARY:", ev["summary"] if a.full else ev["summary"][:1200])
            if ev["kind"] == "post":
                print(f"\n--- post-compaction message (rewritten={ev['rewritten']})")
                print(ev["placed_message"] if a.full else ev["placed_message"][:1500])
        print("\nscores:", {k: v.value for k, v in (s.scores or {}).items()})


if __name__ == "__main__":
    main()
