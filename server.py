#!/usr/bin/env python3
"""Minimal HTTP server: routes from parse.jq; GET / -> index.jq, POST / -> run.jq (YAML->JSON), POST /state -> state.jq."""
import json
import logging
import os
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import yaml

logger = logging.getLogger("jqyml")

# Max request body size (1MB) to avoid OOM on large payloads
MAX_BODY_SIZE = 1_000_000

# Lock for state read-modify-write to avoid lost increments under concurrency
_state_lock = threading.Lock()


def _log_jq_stderr(stderr: str) -> None:
    """Forward jq stderr (DEBUG|... or slog JSON) to Python logging."""
    if not (stderr and stderr.strip()):
        return
    for line in stderr.strip().splitlines():
        s = line.strip()
        if s.startswith("DEBUG|"):
            s = s[6:].strip()
        elif s.startswith("DEBUG:"):
            s = s[6:].strip()
        else:
            logger.debug("jq: %s", line)
            continue
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and "msg" in obj:
                level = (obj.get("level") or "info").lower()
                msg = obj.get("msg", "")
                attrs = {k: v for k, v in obj.items() if k not in ("level", "msg")}
                log_fn = getattr(logger, level, logger.info)
                if attrs:
                    log_fn("%s %s", msg, attrs)
                else:
                    log_fn("%s", msg)
            else:
                logger.debug("%s", s)
        except json.JSONDecodeError:
            logger.debug("jq: %s", s)

NOT_FOUND_VARS = {
    "status": "404",
    "message": "Not Found.",
    "explanation": "404 - Nothing matches the given URI.",
}
UNAUTHORIZED_VARS = {
    "status": "401",
    "message": "Unauthorized.",
    "explanation": "401 - Unauthorized route or invalid credentials.",
}
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "state.yml")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
FAVICON_PATH = os.path.join(APP_DIR, "favicon.ico")
# Use /app in Docker, else APP_DIR for local runs (e.g. make test-server)
APP_ROOT = "/app" if os.path.exists("/app") else APP_DIR


def _jq_cmd(base: list) -> list:
    """Return jq command with paths under APP_ROOT. base is [jq, -L, /app]; we emit [jq, -L, APP_ROOT] and do not re-append the path (jq would treat it as an input file)."""
    return [base[0], "-L", APP_ROOT] + [
        arg.replace("/app", APP_ROOT) for arg in base[3:]
    ]


JQ_BASE = ["jq", "-L", "/app"]
JQ = _jq_cmd(JQ_BASE)
RUN_JQ = JQ + ["-R", "-s", "-f", os.path.join(APP_ROOT, "run.jq")]
INDEX_JQ = JQ + ["-n", "-r", "-f", os.path.join(APP_ROOT, "index.jq")]
INDEX_JQX = JQ + [
    "-r", "--rawfile", "tmpl", os.path.join(APP_ROOT, "index.jqx"),
    "--rawfile", "header", os.path.join(APP_ROOT, "header.jqx"),
    "--rawfile", "head", os.path.join(APP_ROOT, "head.jqx"),
    "-f", os.path.join(APP_ROOT, "jqx.jq"),
]
INDEX_OLD_JQ = JQ + ["-n", "-r", "-f", os.path.join(APP_ROOT, "index_old.jq")]
STATE_JQ = JQ + ["-f", os.path.join(APP_ROOT, "state.jq")]
_EMPTY_JQX = os.path.join(APP_ROOT, "empty.jqx")
NOT_FOUND_JQ = JQ + ["-r", "--rawfile", "tmpl", os.path.join(APP_ROOT, "404.jqx"), "--rawfile", "header", _EMPTY_JQX, "--rawfile", "head", _EMPTY_JQX, "-f", os.path.join(APP_ROOT, "jqx.jq")]
BAD_REQUEST_JQ = JQ + ["-r", "--rawfile", "tmpl", os.path.join(APP_ROOT, "400.jqx"), "--rawfile", "header", _EMPTY_JQX, "--rawfile", "head", _EMPTY_JQX, "-f", os.path.join(APP_ROOT, "jqx.jq")]
UNAUTHORIZED_JQ = JQ + ["-r", "--rawfile", "tmpl", os.path.join(APP_ROOT, "401.jqx"), "--rawfile", "header", _EMPTY_JQX, "--rawfile", "head", _EMPTY_JQX, "-f", os.path.join(APP_ROOT, "jqx.jq")]
PARSE_JQ = JQ + ["-f", os.path.join(APP_ROOT, "parse.jq")]


def parse_route(method: str, path: str, body: str) -> dict:
    """Route request to action; matches parse.jq logic without subprocess."""
    p = path.split("?")[0]
    if method == "GET" and p in ("/", "/index.html"):
        return {"action": "index"}
    if method == "GET" and p == "/old":
        return {"action": "index_old"}
    if method == "GET" and p == "/admin":
        return {"action": "unauthorized"}
    if method == "GET" and p == "/state":
        return {"action": "state_read"}
    if method == "GET" and p == "/favicon.ico":
        return {"action": "favicon"}
    if method == "POST" and p == "/":
        return {"action": "convert", "body": body or ""}
    if method == "POST" and p == "/state":
        return {"action": "state", "body": body or ""}
    return {"action": "not_found"}


class Handler(BaseHTTPRequestHandler):
    def parse_route(self, method: str, path: str, body: str) -> dict:
        return parse_route(method, path, body)

    def send_404(self):
        try:
            r = subprocess.run(
                NOT_FOUND_JQ,
                input=json.dumps(NOT_FOUND_VARS),
                capture_output=True,
                text=True,
                timeout=2,
                cwd=APP_ROOT,
            )
            _log_jq_stderr(r.stderr or "")
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
                cwd=APP_ROOT,
            )
            _log_jq_stderr(r.stderr or "")
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
                cwd=APP_ROOT,
            )
            _log_jq_stderr(r.stderr or "")
            body = r.stdout if r.returncode == 0 else "401 Unauthorized"
        except Exception:
            body = "401 Unauthorized"
        self.send_response(401)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _get_current_state(self) -> dict:
        """Return current state (e.g. from state.yml); default counter 0."""
        if not os.path.isfile(STATE_PATH):
            return {"counter": 0}
        try:
            with open(STATE_PATH) as f:
                yaml_raw = f.read()
            r = subprocess.run(
                RUN_JQ,
                input=yaml_raw,
                capture_output=True,
                text=True,
                timeout=5,
                cwd=APP_ROOT,
            )
            _log_jq_stderr(r.stderr or "")
            if r.returncode != 0:
                return {"counter": 0}
            state = json.loads(r.stdout)
            if "counter" not in state:
                state["counter"] = 0
            return state
        except Exception:
            return {"counter": 0}

    def do_GET(self):
        route = self.parse_route("GET", self.path, "")
        if route["action"] == "index":
            try:
                state = self._get_current_state()
                count = state.get("counter", 0)
                index_vars = {
                    "count": count,
                    "count_is_zero": count == 0,
                    "count_gt_0": count > 0,
                }
                r = subprocess.run(
                    INDEX_JQX,
                    input=json.dumps(index_vars),
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=APP_ROOT,
                )
                _log_jq_stderr(r.stderr or "")
                out = r.stdout if r.returncode == 0 else r.stderr or "error"
                status = 200 if r.returncode == 0 else 500
                if r.returncode != 0:
                    logger.error("index.jqx jq exit %s stderr: %s", r.returncode, (r.stderr or "")[:500])
                if r.returncode == 0 and (not out or not out.strip()):
                    logger.error("index.jqx produced empty output; returning 500")
                    out, status = "index.jqx produced empty output", 500
            except Exception as e:
                logger.exception("index render failed")
                out, status = str(e), 500
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(out.encode("utf-8"))
        elif route["action"] == "index_old":
            try:
                r = subprocess.run(INDEX_OLD_JQ, capture_output=True, text=True, timeout=5, cwd=APP_ROOT)
                _log_jq_stderr(r.stderr or "")
                out = r.stdout if r.returncode == 0 else r.stderr or "error"
                status = 200 if r.returncode == 0 else 500
            except Exception as e:
                logger.exception("index_old failed")
                out, status = str(e), 500
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(out.encode("utf-8"))
        elif route["action"] == "unauthorized":
            self.send_401()
        elif route["action"] == "state_read":
            try:
                state = self._get_current_state()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(state).encode())
            except Exception as e:
                logger.exception("GET /state failed")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"message": str(e)}).encode())
        elif route["action"] == "favicon":
            favicon = os.path.join(APP_ROOT, "favicon.ico")
            if os.path.isfile(favicon):
                with open(favicon, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/x-icon")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_404()
        else:
            self.send_404()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_SIZE:
            logger.warning("body size %s exceeds limit %s", length, MAX_BODY_SIZE)
            self.send_response(413)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"message": "Request entity too large"}).encode())
            return
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
                _log_jq_stderr(r.stderr or "")
                out = r.stdout if r.returncode == 0 else r.stderr or r.stdout
                status = 200 if r.returncode == 0 else 400
            except subprocess.TimeoutExpired:
                logger.error("POST / convert timeout")
                out, status = "timeout", 408
            except Exception as e:
                logger.exception("POST / convert failed")
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
                with _state_lock:
                    if os.path.isfile(STATE_PATH):
                        with open(STATE_PATH) as f:
                            yaml_raw = f.read()
                        r = subprocess.run(
                            RUN_JQ,
                            input=yaml_raw,
                            capture_output=True,
                            text=True,
                            timeout=5,
                            cwd=APP_ROOT,
                        )
                        _log_jq_stderr(r.stderr or "")
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
                        cwd=APP_ROOT,
                    )
                    _log_jq_stderr(r.stderr or "")
                    if r.returncode != 0:
                        logger.error("state.jq failed: %s", r.stderr or "unknown")
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
                logger.exception("POST /state failed")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"message": str(e)}).encode())
        else:
            self.send_404()

    def log_message(self, format, *args):
        logger.info(format % args)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    port = int(os.environ.get("PORT", "8888"))
    HTTPServer(("", port), Handler).serve_forever()
