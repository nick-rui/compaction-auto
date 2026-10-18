"""The continuation line, powered up. Per scenario, thinking-agent decision on REAL states.
python -m exp.reality.report4"""

from scipy.stats import fisher_exact

from exp.reality import analyze as A
from exp.reality import common as K
from exp.reality.report import load

PH = ["posthoc_k2.jsonl", "posthoc_k2ns.jsonl", "posthoc_placeedit.jsonl", "posthoc_concrete.jsonl",
      "posthoc_power.jsonl", "posthoc_wording.jsonl"]
CELLS = [("as-is (Claude Code line)", "asis"), ("+ fact in system prompt", "sys_edit"), ("- line", "asis_ns"),
         ("+ sys fact - line", "d:sys+ns"), ("line -> 'Continue the task.'", "d:neutral"),
         ("line -> safety-aware", "d:safe"), ("+ sys fact, line -> safety-aware", "d:sys+safe")]


def cell(ds):
    n = len(ds)
    h = sum(d["harm"] for d in ds)
    a = sum(d["asked"] for d in ds)
    return h, a, n


def main():
    full = A.rows_full()
    rows, seen = [], set()
    for f in PH:
        for r in load(f):
            key = (r["scn"], r["chain"], r["mode"], r.get("rep", 0))
            if r["cond"] == "REAL" and r.get("decision") and key not in seen:
                seen.add(key)
                rows.append(r)
    fl = load("full_line.jsonl") + load("full_line2.jsonl") + load("full_line3.jsonl")  # same design, pooled
    out = []
    for scns in (("store",), ("crm",), ("store", "crm")):
        tag = "+".join(scns)
        print(f"\n=== {tag} ===")
        fd = [r["decision"] for r in full if r["cond"] == "REAL" and r["scn"] in scns and r.get("decision")]
        base = cell(fd)
        table = [("full history", base)]
        for lab, var in [("full + line appended to decision msg", "final"), ("full + line as own user turn", "pos"),
                         ("full + compaction-style user msg", "cmsg"), ("full + line as system note", "sysnote")]:
            table.append((lab, cell([r["decision"] for r in fl if r["var"] == var and r["scn"] in scns])))
        for lab, mode in CELLS:
            table.append((f"k=2 {lab}", cell([r["decision"] for r in rows if r["mode"] == mode and r["scn"] in scns])))
        for lab, (h, a, n) in table:
            if n == 0:
                continue
            p = fisher_exact([[base[0], base[2] - base[0]], [h, n - h]])[1] if lab != "full history" else float("nan")
            print(f"  {lab:38s} harm {K.fmt(h, n):>20s}  asks-first {K.fmt(a, n):>20s}  (harm vs full p={p:.3g})")
            out.append((tag, lab, h, a, n))
    return out


if __name__ == "__main__":
    main()
