#!/usr/bin/env python3
"""Minimal HTTP server: routes from parse.jq; GET / -> index.jq, POST / -> run.jq (YAML->JSON)."""
import json
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

JQ = ["jq", "-L", "/app"]
RUN_JQ = JQ + ["-R", "-s", "-f", "/app/run.jq"]
INDEX_JQ = JQ + ["-n", "-r", "-f", "/app/index.jq"]
INDEX_OLD_JQ = JQ + ["-n", "-r", "-f", "/app/index_old.jq"]
NOT_FOUND_JQ = JQ + ["-n", "-r", "-f", "/app/404.jq"]
PARSE_JQ = JQ + ["-f", "/app/parse.jq"]


class Handler(BaseHTTPRequestHandler):
    def parse_route(self, method: str, path: str, body: str) -> dict:
        request = {"method": method, "path": path, "body": body}
        r = subprocess.run(
            PARSE_JQ,
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode != 0:
            return {"action": "not_found"}
        return json.loads(r.stdout)

    def send_404(self):
        try:
            r = subprocess.run(NOT_FOUND_JQ, capture_output=True, text=True, timeout=2, cwd="/app")
            body = r.stdout if r.returncode == 0 else "404 Not Found"
        except Exception:
            body = "404 Not Found"
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        route = self.parse_route("GET", self.path, "")
        if route["action"] == "index":
            try:
                r = subprocess.run(INDEX_JQ, capture_output=True, text=True, timeout=5, cwd="/app")
                out = r.stdout if r.returncode == 0 else r.stderr or "error"
                status = 200 if r.returncode == 0 else 500
            except Exception as e:
                out, status = str(e), 500
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(out.encode("utf-8"))
        elif route["action"] == "index_old":
            try:
                r = subprocess.run(INDEX_OLD_JQ, capture_output=True, text=True, timeout=5, cwd="/app")
                out = r.stdout if r.returncode == 0 else r.stderr or "error"
                status = 200 if r.returncode == 0 else 500
            except Exception as e:
                out, status = str(e), 500
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(out.encode("utf-8"))
        else:
            self.send_404()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        route = self.parse_route("POST", self.path, body)
        if route["action"] == "convert":
            try:
                r = subprocess.run(
                    RUN_JQ,
                    input=route.get("body", ""),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                out = r.stdout if r.returncode == 0 else r.stderr or r.stdout
                status = 200 if r.returncode == 0 else 400
            except subprocess.TimeoutExpired:
                out, status = "timeout", 408
            except Exception as e:
                out, status = str(e), 500
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out.encode("utf-8"))
        else:
            self.send_404()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("", 8888), Handler).serve_forever()
