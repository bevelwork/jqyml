#!/usr/bin/env python3
"""Minimal HTTP server: routes from parse.jq; GET / -> index.jq, POST / -> run.jq (YAML->JSON), POST /state -> state.jq."""
import json
import os
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

import yaml

JQ = ["jq", "-L", "/app"]
RUN_JQ = JQ + ["-R", "-s", "-f", "/app/run.jq"]
INDEX_JQ = JQ + ["-n", "-r", "-f", "/app/index.jq"]
INDEX_OLD_JQ = JQ + ["-n", "-r", "-f", "/app/index_old.jq"]
STATE_JQ = JQ + ["-f", "/app/state.jq"]
NOT_FOUND_JQ = JQ + ["-r", "--rawfile", "tmpl", "/app/404.jqx", "-f", "/app/jqx.jq"]
NOT_FOUND_VARS = {
    "error_code": "404",
    "message": "Not Found.",
    "explanation": "404 - Nothing matches the given URI.",
}
BAD_REQUEST_JQ = JQ + ["-r", "--rawfile", "tmpl", "/app/400.jqx", "-f", "/app/jqx.jq"]
UNAUTHORIZED_JQ = JQ + ["-r", "--rawfile", "tmpl", "/app/401.jqx", "-f", "/app/jqx.jq"]
UNAUTHORIZED_VARS = {
    "status": "401",
    "message": "Unauthorized.",
    "explanation": "401 - Unauthorized route or invalid credentials.",
}
PARSE_JQ = JQ + ["-f", "/app/parse.jq"]
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "state.yml")


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
            r = subprocess.run(
                NOT_FOUND_JQ,
                input=json.dumps(NOT_FOUND_VARS),
                capture_output=True,
                text=True,
                timeout=2,
                cwd="/app",
            )
            body = r.stdout if r.returncode == 0 else "404 Not Found"
        except Exception:
            body = "404 Not Found"
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def send_400(self, message: str, explanation: str = "400 - Bad Request / invalid user input."):
        vars_ = {"status": "400", "message": message, "explanation": explanation}
        try:
            r = subprocess.run(
                BAD_REQUEST_JQ,
                input=json.dumps(vars_),
                capture_output=True,
                text=True,
                timeout=2,
                cwd="/app",
            )
            body = r.stdout if r.returncode == 0 else f"400 Bad Request: {message}"
        except Exception:
            body = f"400 Bad Request: {message}"
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def send_401(self):
        try:
            r = subprocess.run(
                UNAUTHORIZED_JQ,
                input=json.dumps(UNAUTHORIZED_VARS),
                capture_output=True,
                text=True,
                timeout=2,
                cwd="/app",
            )
            body = r.stdout if r.returncode == 0 else "401 Unauthorized"
        except Exception:
            body = "401 Unauthorized"
        self.send_response(401)
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
        elif route["action"] == "unauthorized":
            self.send_401()
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
        elif route["action"] == "state":
            try:
                body_obj = json.loads(body) if body.strip() else {}
            except json.JSONDecodeError:
                self.send_400("Body must be valid JSON.")
                return
            headers_lower = {k.lower(): v for k, v in self.headers.items()}
            try:
                if os.path.isfile(STATE_PATH):
                    with open(STATE_PATH) as f:
                        yaml_raw = f.read()
                    r = subprocess.run(
                        RUN_JQ,
                        input=yaml_raw,
                        capture_output=True,
                        text=True,
                        timeout=5,
                        cwd="/app",
                    )
                    current_state = json.loads(r.stdout) if r.returncode == 0 else {}
                else:
                    current_state = {"counter": 0}
                if "counter" not in current_state:
                    current_state["counter"] = 0
                state_input = {
                    "request": {
                        "method": "POST",
                        "path": "/state",
                        "headers": headers_lower,
                        "body": body_obj,
                    },
                    "current_state": current_state,
                }
                r = subprocess.run(
                    STATE_JQ,
                    input=json.dumps(state_input),
                    capture_output=True,
                    text=True,
                    timeout=2,
                    cwd="/app",
                )
                if r.returncode != 0:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"message": r.stderr or "state.jq failed"}).encode())
                    return
                result = json.loads(r.stdout)
                if result.get("valid"):
                    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
                    with open(STATE_PATH, "w") as f:
                        yaml.dump(result["new_state"], f, default_flow_style=False, sort_keys=False)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result["new_state"]).encode())
                else:
                    status = result.get("status", 400)
                    msg = result.get("message", "validation failed")
                    if status == 401:
                        self.send_401()
                    else:
                        self.send_400(msg)
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"message": str(e)}).encode())
        else:
            self.send_404()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("", 8888), Handler).serve_forever()
