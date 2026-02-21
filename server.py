#!/usr/bin/env python3
"""Minimal HTTP server: GET / -> index (index.jq), POST body (YAML) -> jq (run.jq) -> JSON."""
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

JQ_CMD = ["jq", "-R", "-s", "-L", "/app", "-f", "/app/run.jq"]
INDEX_CMD = ["jq", "-n", "-r", "-L", "/app", "-f", "/app/index.jq"]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/" and self.path != "/index.html":
            self.send_error(404)
            return
        try:
            r = subprocess.run(INDEX_CMD, capture_output=True, text=True, timeout=5, cwd="/app")
            out = r.stdout if r.returncode == 0 else r.stderr or "error"
            status = 200 if r.returncode == 0 else 500
        except Exception as e:
            out, status = str(e), 500
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(out.encode("utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            r = subprocess.run(
                JQ_CMD,
                input=body,
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

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    HTTPServer(("", 8888), Handler).serve_forever()
