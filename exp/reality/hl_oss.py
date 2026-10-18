"""Does SELF-compaction (current CA_MODEL as compactor) keep exp/halflife's refusal fact (type d), and does the
successor publish the withheld post? Uses exp/halflife's history/filler/probe/scoring code read-only; writes to
REALITY_RES/hl_chains.jsonl. Chain exactly as exp/halflife (compact_chain, style claude, fixed=True), K=2.
python -m exp.reality.hl_oss --n 6"""
import argparse, asyncio, os
from exp.reality import common as K  # noqa: F401  (concurrency cap)
from ca import compact as C
from exp.halflife import common as HU
from exp.halflife import scen as HS

OUT = os.path.join(K.RES, "hl_chains.jsonl")


async def one(dom, seed, K_):
    H, order = HS.build_history(dom, seed)
    X0 = H + HS.filler(dom, 0)
    res = await C.compact_chain(X0, K_, style="claude", between=lambda r, h: HS.filler(dom, r + 1))
    sums = [s["summary"] for s, _ in res]
    beh = {}
    for k in range(1, K_ + 1):
        ctx = HU.compacted_state(dom, seed, sums, k, "claude")
        beh[k] = await HU.behave(ctx, dom, "d", think=K.OSS)
    full = await HU.behave(HU.full_state(dom, seed, K_), dom, "d", think=K.OSS)
    K.dump(OUT, [dict(dom=dom, seed=seed, summaries=sums, regex=[HU.regex_facts(dom, s) for s in sums],
                      violate={k: b["violate"] for k, b in beh.items()}, full_violate=full["violate"],
                      calls={k: b["calls"] for k, b in beh.items()})])


async def main(a):
    await asyncio.gather(*[one(d, s, a.K) for d in HS.DOMAINS for s in range(a.n)])
    print("done")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=6)
    p.add_argument("--K", type=int, default=2)
    asyncio.run(main(p.parse_args()))
