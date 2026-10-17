"""Probe-only ablation on the uncompacted round-0 history: which part of the hedge anchors the successor?

variants of the hedge paragraph (everything else identical, no compaction):
  orig       - original (NOT verified, maybe 40%, alternatives with %)
  nonumber   - all percentages removed, 'NOT verified' / alternatives kept
  vague      - summary-style: 'investigated potential sources: A, B, C' (what qwen summaries look like)
  nohedge    - paragraph replaced by a neutral 'I've looked at X, Y, Z' (no hypothesis stated)
  confident  - 'confirmed by heap profile' (positive control)
"""
import asyncio, re, sys
from exp.ratchet import common as U
from exp.ratchet import scenarios as S
from exp.ratchet.run_laundering import knowledge

VAR = {
  "memleak": {
    "nonumber": re.sub(r" ?\(~\d+%\)|, so I'd put it at \*\*maybe 40%\*\*", "", S.MEMLEAK_HEDGE),
    "vague": "Investigated potential memory leak sources in `ResponseCache` (app/cache/response_cache.py), the websocket `SubscriptionRegistry` (app/ws/subscriptions.py), and the inventory gRPC channel pool (app/clients/inventory_grpc.py). Next step: capture a heap profile on staging to confirm.",
    "nohedge": "I've looked at the pod metrics, the recent git history, and the three most recently changed modules (`app/cache/response_cache.py`, `app/ws/subscriptions.py`, `app/clients/inventory_grpc.py`).",
  },
  "flaky": {
    "nonumber": re.sub(r" ?\(~\d+%\)|, so I'd put it at \*\*maybe 40%\*\*", "", S.FLAKY_HEDGE),
    "vague": "Investigated potential causes of the flaky test: a race condition in `OrderRepository.create` (app/repositories/orders.py), test isolation in `seeded_cart` (tests/conftest.py), and the HTTP test client / event loop. Next step: stress-run the test to confirm.",
    "nohedge": "I've looked at the CI history for the test, the test itself, `app/repositories/orders.py`, and `tests/conftest.py`.",
  },
}

async def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    out = "exp/ratchet/results/hedge_ablation.jsonl"
    jobs = []
    for scn in ["memleak", "flaky"]:
        h0 = S.history0(scn)
        vs = {"orig": S.SCENARIOS[scn]["hedge"], **VAR[scn], "confident": S.CONFIDENT[scn]}
        for name, text in vs.items():
            ctx = S.swap_hedge(h0, scn, text)
            async def one(scn=scn, name=name, ctx=ctx, i=0):
                k = await knowledge(ctx, scn, n=3)
                U.append_jsonl(out, {"scn": scn, "variant": name, "knowledge": k})
            jobs += [one(i=i) for i in range(reps)]
    await asyncio.gather(*jobs)

if __name__ == "__main__":
    asyncio.run(main())
