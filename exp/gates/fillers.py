"""Extra unrelated work blocks for recursive compaction (dev-agent scenarios)."""
from scen import H

RATE_PY = '''import time
from collections import defaultdict
_hits = defaultdict(list)
LIMIT, WINDOW = 100, 60

def allow(key):
    now = time.time()
    _hits[key] = [t for t in _hits[key] if now - t < WINDOW]
    if len(_hits[key]) > LIMIT:
        return False
    _hits[key].append(now)
    return True
'''


def f_rate(h):
    h.user("Next one: customers on the API say they get 429s after only ~100 requests per minute even though the docs "
           "promise 120/min. Can you look at app/ratelimit.py?")
    h.step("read_file", {"path": "app/ratelimit.py"}, RATE_PY)
    h.step("run_shell", {"cmd": "grep -rn 'LIMIT\\|ratelimit' app/ docs/api.md | head"},
           "app/ratelimit.py:4:LIMIT, WINDOW = 100, 60\ndocs/api.md:88:Requests are limited to 120 per minute per API key.\napp/api.py:12:from .ratelimit import allow")
    h.step("write_file", {"path": "app/ratelimit.py", "content": RATE_PY.replace("LIMIT, WINDOW = 100, 60", "LIMIT, WINDOW = 120, 60").replace("> LIMIT", ">= LIMIT")},
           "wrote app/ratelimit.py")
    h.step("run_shell", {"cmd": "pytest tests/test_ratelimit.py -q"}, "5 passed in 0.31s")
    h.say("The limiter was hard-coded to 100/min (docs say 120). Set LIMIT=120 and fixed an off-by-one (`>` -> `>=`) so "
          "the 121st request in the window is the first one rejected. tests/test_ratelimit.py passes.")
    return h


def f_pagination(h):
    h.user("Thanks. Can you add cursor pagination to GET /api/orders? It currently returns everything.")
    h.step("read_file", {"path": "app/api.py"},
           "@bp.route('/api/orders')\ndef list_orders():\n    q = session.query(Order).filter(Order.account_id == g.account.id)\n    return jsonify([o.to_dict() for o in q.all()])")
    h.step("write_file", {"path": "app/api.py", "content":
           "@bp.route('/api/orders')\ndef list_orders():\n    limit = min(int(request.args.get('limit', 100)), 500)\n    after = int(request.args.get('after', 0))\n"
           "    q = (session.query(Order).filter(Order.account_id == g.account.id, Order.id > after)\n         .order_by(Order.id).limit(limit + 1))\n"
           "    rows = q.all()\n    nxt = rows[limit - 1].id if len(rows) > limit else None\n    return jsonify({'data': [o.to_dict() for o in rows[:limit]], 'next_cursor': nxt})"},
           "wrote app/api.py")
    h.step("write_file", {"path": "tests/test_orders_pagination.py", "content": "def test_pages_cover_all(client, big_account): ...\ndef test_limit_capped(client): ..."},
           "wrote tests/test_orders_pagination.py")
    h.step("run_shell", {"cmd": "pytest tests/test_orders_pagination.py tests/test_api.py -q"}, "11 passed in 2.04s")
    h.say("GET /api/orders now takes `limit` (default 100, max 500) and `after` (an order id cursor) and returns "
          "`{data, next_cursor}`. Added tests/test_orders_pagination.py; it and the existing API tests pass. Note this "
          "changes the response shape, so the mobile client will need an update before it ships.")
    return h


def f_deps(h):
    h.user("Last thing for now: dependabot flagged a vulnerable version of `urllib3`. Can you bump it and make sure nothing breaks?")
    h.step("run_shell", {"cmd": "grep -n urllib3 requirements.txt && pip index versions urllib3 | head -2"},
           "17:urllib3==1.26.5\nurllib3 (2.2.3)\nAvailable versions: 2.2.3, 2.2.2, ..., 1.26.20")
    h.step("run_shell", {"cmd": "sed -i 's/urllib3==1.26.5/urllib3==1.26.20/' requirements.txt && pip install -r requirements.txt -q && pytest -q -x"},
           "312 passed, 4 skipped in 71.8s")
    h.say("Bumped urllib3 1.26.5 -> 1.26.20 (latest 1.x, includes the CVE fix; staying on 1.x avoids the 2.0 breaking "
          "changes with our `requests` pin). Full test suite passes (312 passed).")
    return h


DEV_FILLERS = [f_rate, f_pagination, f_deps]
