"""Mock external services for the sandbox (stdlib only).

Routes come from /opt/ce/routes/*.json, each a list of:
  {"method": "POST", "path": "/deploy", "status": 200, "body": {...} | "text",
   "content_type": "application/json", "delay": 0}
`path` may end in "*" for a prefix match. Unmatched requests get 404.

Every request is appended to /var/log/ce/requests.jsonl as
  {"t": ..., "method": ..., "path": ..., "query": ..., "body": ..., "status": ...}
so scorers can check exactly what the agent did. Listens on 127.0.0.1:${CE_MOCK_PORT:-8080}.
"""

import glob
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LOG = "/var/log/ce/requests.jsonl"


def load_routes():
    routes = []
    for f in sorted(glob.glob("/opt/ce/routes/*.json")):
        with open(f) as fh:
            routes.extend(json.load(fh))
    return routes


def match(routes, method, path):
    for r in routes:
        if r.get("method", "GET").upper() not in (method, "*"):
            continue
        p = r["path"]
        if (p.endswith("*") and path.startswith(p[:-1])) or p == path:
            return r
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _handle(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        try:
            body = json.loads(raw) if raw else None
        except Exception:
            body = raw
        r = match(load_routes(), self.command, u.path)
        status = r.get("status", 200) if r else 404
        with open(LOG, "a") as fh:
            fh.write(json.dumps({"t": time.time(), "method": self.command, "path": u.path,
                                 "query": parse_qs(u.query), "body": body, "status": status}) + "\n")
        if r and r.get("delay"):
            time.sleep(float(r["delay"]))
        payload = (r or {}).get("body", {"error": "not found"})
        if isinstance(payload, (dict, list)):
            out, ctype = json.dumps(payload).encode(), "application/json"
        else:
            out, ctype = str(payload).encode(), (r or {}).get("content_type", "text/plain")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _handle


if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    port = int(os.environ.get("CE_MOCK_PORT", "8080"))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
