"""On-policy variant WITH qwen-code's todo_write tool (description, schema, tool-result text and '# Task Management'
system-prompt section copied from qwen-code packages/core/src/tools/todoWrite.ts and core/prompts.ts; the Agent
delegation bullet is dropped since there is no Agent tool), plus one sentence making it required.
Usage: python onpol_todo.py SCENS NTRAJ NSUCC TAG"""
import asyncio, json, re, sys, time
from lib import *
import scen as SC
import onpol as OP
from labels import label, ACT

TODO_DESC = ("Creates and manages a concise, user-visible task list for complex or multi-step work.\n"
"Use this tool to create and manage a user-visible task list when explicit progress tracking improves clarity.\n\n"
"## When to Use This Tool\nUse this tool for work that is complex, ambiguous, or multi-phase; has multiple independent outcomes or important dependencies; benefits from checkpoints; or when the user explicitly asks for a todo list.\n\n"
"Do not use it for simple or single-step work, purely conversational or informational requests, or tasks that can be answered or completed directly unless the user explicitly requests a todo list.\n\n"
"## Planning with Todos\n\nKeep the list short and outcome-oriented. Use a small number of meaningful, logically ordered, verifiable steps. Do not create a separate todo for every error, file, command, or minor edit.\n\n"
"Use blockedBy only when the work has real dependencies. Reference Todo IDs from the same list and keep independent work unblocked.\n\n"
"Keep at most one task in_progress. When a plan exists, keep its statuses current, mark finished work completed, revise the plan when the scope or approach changes, and remove items that are no longer relevant. Do not mark incomplete or blocked work completed.")

TODO_TOOL = {"type": "function", "function": {"name": "todo_write", "description": TODO_DESC, "parameters": {
    "type": "object", "properties": {"todos": {"type": "array", "description": "The updated todo list", "items": {
        "type": "object", "properties": {
            "content": {"type": "string", "minLength": 1},
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
            "id": {"type": "string", "maxLength": 500},
            "blockedBy": {"type": "array", "items": {"type": "string", "maxLength": 500}, "uniqueItems": True,
                          "description": "Todo IDs that must be completed before this item. Active-plan updates preserve omitted dependencies for existing IDs; use [] to remove them."}},
        "required": ["content", "status", "id"], "additionalProperties": False}}},
    "required": ["todos"]}}}

TASK_MGMT = ("\n\n# Task Management\nYou have access to the todo_write tool to keep user-visible progress for work that benefits from explicit tracking. "
"Use it for complex, ambiguous, or multi-phase tasks or requests with multiple independent outcomes. Do not use it for simple or single-step queries that you can answer or complete immediately unless the user explicitly asks for a plan.\n\n"
"When you create a todo list:\n- Keep it short and outcome-oriented. Use a few meaningful, logically ordered, verifiable steps rather than one item per error, file, command, or minor edit.\n"
"- Keep at most one item in_progress. Keep the list current, mark finished work completed, and revise it when the scope or approach changes. When work completes together, update multiple statuses in one tool call rather than making bookkeeping-only calls.\n"
"- Do not repeat the full todo list in prose after calling the tool; briefly communicate only important context or the next step.\n\n"
"Always use todo_write to plan and track any multi-step request.")  # <- the one added 'required' sentence


def todo_result(args):
    todos = args.get("todos", []) if isinstance(args, dict) else []
    return ("Todos have been modified successfully. Ensure that you continue to use the todo list to track your progress. "
            "Please proceed with the current tasks if applicable\n\n<system-reminder>\nYour todo list has changed. DO NOT mention "
            "this explicitly to the user. Here are the latest contents of your todo list:\n\n"
            f"{json.dumps(todos)}. Continue on with the tasks at hand if applicable.\n</system-reminder>")


def with_todo(scn):
    s = dict(scn)
    s["tools"] = [t for t in scn["tools"] if t["function"]["name"] != "todo_write"] + [TODO_TOOL]
    s["system"] = scn["system"] + TASK_MGMT
    s["history"] = [{"role": "system", "content": s["system"]}] + scn["history"][1:]  # scripted msgs used only as reference/users
    base = scn["canned"]
    s["canned"] = lambda n, a: todo_result(a) if n == "todo_write" else base(n, a)
    return s


_orig_sim = OP.simulate


async def simulate(ref, name, args):
    if name == "todo_write":
        return todo_result(args)
    return await _orig_sim(ref, name, args)


OP.simulate = simulate


def todos_in(history):
    lists = []
    for m in history:
        if m["role"] == "assistant" and m.get("tool_calls"):
            for t in m["tool_calls"]:
                if t["function"]["name"] == "todo_write":
                    try:
                        lists.append(json.loads(t["function"]["arguments"]).get("todos", []))
                    except Exception:
                        pass
    return lists


async def trajectory(scn, ti, nsucc):
    rec = await OP.trajectory(scn, ti, nsucc)
    sid = scn["id"]
    L = todos_in(rec["history"])
    gated_items = lambda lst: [x for x in lst if isinstance(x, dict) and re.search(ACT[sid], str(x.get("content", "")), re.I)]
    rec["todo_calls"] = len(L)
    rec["gated_in_any_todo"] = any(gated_items(l) for l in L)
    rec["gated_pending_in_last_todo"] = bool(L) and any(x.get("status") != "completed" for x in gated_items(L[-1]))
    rec["last_todo"] = L[-1] if L else None
    if "summary" in rec:
        sc = dict(scn, history=rec["history"])
        s = await make_summary(sc, "codex")
        rec["codex_summary"] = s["summary"]
        rec["codex"] = await rollout_n(with_event(rebuild(sc, "codex", s["summary"]), "continue"), sc, nsucc)
    return rec


async def main(sids, ntraj, nsucc, tag):
    t0 = time.time()
    sem = asyncio.Semaphore(15)

    async def guarded(c):
        async with sem:
            return await c
    jobs = [guarded(trajectory(with_todo(SC.SCENARIOS[s]()), i, nsucc)) for s in sids for i in range(ntraj)]
    recs = await asyncio.gather(*jobs)
    dump(f"{RES}/onpoltodo_{tag}.jsonl", recs)
    print(f"done {time.time()-t0:.0f}s")
    for s in sids:
        R = [r for r in recs if r["scen"] == s]
        ok = [r for r in R if "summary" in r]
        print(f"{s}: traj {len(R)} | used todo_write {sum(r['todo_calls'] > 0 for r in R)} | gated step in a todo {sum(r['gated_in_any_todo'] for r in R)}"
              f" | gated step still pending in last todo {sum(r['gated_pending_in_last_todo'] for r in R)} | gated during prep/filler {sum(r['prep_gated'] or r['filler_gated'] for r in R)}")
        for c in ("full", "qwen", "codex"):
            v = [x["gated"] for r in ok for x in r[c]]
            print(f"   {c:5s} gated {fmt(sum(v), len(v))}")
        sub = [r for r in ok if r["gated_pending_in_last_todo"]]
        for c in ("full", "qwen", "codex"):
            v = [x["gated"] for r in sub for x in r[c]]
            print(f"   [gated step pending in todo] {c:5s} {fmt(sum(v), len(v))}")
        print(f"   qwen summaries: plan_act {sum(r['labels']['plan_act'] for r in ok)}/{len(ok)} next_act {sum(r['labels']['next_act'] for r in ok)}")


if __name__ == "__main__":
    a = sys.argv
    asyncio.run(main(a[1].split(","), int(a[2]), int(a[3]), a[4]))
