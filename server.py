#!/usr/bin/env python3
import base64
import hashlib
import html as html_module
import json
import logging
import os
import struct
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import yaml

# WebSocket (RFC 6455): handshake and text-frame helpers for /doom/ws
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _ws_accept_key(key: str) -> str:
    """Compute Sec-WebSocket-Accept from Sec-WebSocket-Key."""
    digest = hashlib.sha1((key.strip() + WS_GUID).encode()).digest()
    return base64.b64encode(digest).decode()


def _ws_read_frame(sock) -> str | None:
    """Read one WebSocket text frame from client (masked). Returns payload as str or None on close/error."""
    try:
        header = sock.recv(2)
        if len(header) < 2:
            return None
        opcode = header[0] & 0x0F
        masked = (header[1] & 0x80) != 0
        length = header[1] & 0x7F
        if length == 126:
            ext = sock.recv(2)
            if len(ext) < 2:
                return None
            length = struct.unpack(">H", ext)[0]
        elif length == 127:
            ext = sock.recv(8)
            if len(ext) < 8:
                return None
            length = struct.unpack(">Q", ext)[0]
        if not masked or length > 1_000_000:
            return None
        mask = sock.recv(4)
        if len(mask) < 4:
            return None
        payload = b""
        while len(payload) < length:
            chunk = sock.recv(min(65536, length - len(payload)))
            if not chunk:
                return None
            payload += chunk
        if opcode == 0x08:  # close
            return None
        data = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))
        return data.decode("utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return None


def _ws_write_frame(sock, payload: str) -> None:
    """Send one WebSocket text frame (unmasked) to client."""
    data = payload.encode("utf-8")
    length = len(data)
    if length < 126:
        header = struct.pack(">BB", 0x81, length)
    elif length < 65536:
        header = struct.pack(">BBH", 0x81, 126, length)
    else:
        header = struct.pack(">BBQ", 0x81, 127, length)
    sock.sendall(header + data)

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
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8888").rstrip("/")


def _robots_txt() -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /state\n"
        "\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
    )


def _sitemap_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url><loc>{SITE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>\n'
        f'  <url><loc>{SITE_URL}/old</loc><changefreq>yearly</changefreq><priority>0.3</priority></url>\n'
        f'  <url><loc>{SITE_URL}/doom</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>\n'
        '</urlset>\n'
    )


def _jq_cmd(base: list) -> list:
    """Return jq command with paths under APP_ROOT. base is [jq, -L, /app]; we emit [jq, -L, APP_ROOT] and do not re-append the path (jq would treat it as an input file)."""
    return [base[0], "-L", APP_ROOT] + [
        arg.replace("/app", APP_ROOT) for arg in base[3:]
    ]


JQ_BASE = ["jq", "-L", "/app"]
JQ = _jq_cmd(JQ_BASE)
RUN_JQ = JQ + ["-R", "-s", "-f", os.path.join(APP_ROOT, "run.jq")]
INDEX_JQ = JQ + ["-n", "-r", "-f", os.path.join(APP_ROOT, "index.jq")]
_EMPTY_JQX = os.path.join(APP_ROOT, "empty.jqx")
INDEX_JQX = JQ + [
    "-r", "--rawfile", "tmpl", os.path.join(APP_ROOT, "index.jqx"),
    "--rawfile", "header", os.path.join(APP_ROOT, "header.jqx"),
    "--rawfile", "head", os.path.join(APP_ROOT, "head.jqx"),
    "--rawfile", "footer", _EMPTY_JQX,
    "-f", os.path.join(APP_ROOT, "jqx.jq"),
]
INDEX_OLD_JQ = JQ + ["-n", "-r", "-f", os.path.join(APP_ROOT, "index_old.jq")]
STATE_JQ = JQ + ["-f", os.path.join(APP_ROOT, "state.jq")]
NOT_FOUND_JQ = JQ + ["-r", "--rawfile", "tmpl", os.path.join(APP_ROOT, "404.jqx"), "--rawfile",
                     "header", _EMPTY_JQX, "--rawfile", "head", _EMPTY_JQX, "--rawfile", "footer", _EMPTY_JQX,
                     "-f", os.path.join(APP_ROOT, "jqx.jq")]
BAD_REQUEST_JQ = JQ + ["-r", "--rawfile", "tmpl", os.path.join(
    APP_ROOT, "400.jqx"), "--rawfile", "header", _EMPTY_JQX, "--rawfile", "head", _EMPTY_JQX, "--rawfile", "footer", _EMPTY_JQX,
    "-f", os.path.join(APP_ROOT, "jqx.jq")]
UNAUTHORIZED_JQ = JQ + ["-r", "--rawfile", "tmpl", os.path.join(
    APP_ROOT, "401.jqx"), "--rawfile", "header", _EMPTY_JQX, "--rawfile", "head", _EMPTY_JQX, "--rawfile", "footer", _EMPTY_JQX,
    "-f", os.path.join(APP_ROOT, "jqx.jq")]
BUILT_WITH_JQX = JQ + [
    "-r", "--rawfile", "tmpl", os.path.join(APP_ROOT, "built_with.jqx"),
    "--rawfile", "header", os.path.join(APP_ROOT, "header.jqx"),
    "--rawfile", "head", os.path.join(APP_ROOT, "head.jqx"),
    "--rawfile", "footer", _EMPTY_JQX,
    "-f", os.path.join(APP_ROOT, "jqx.jq"),
]
BUILT_WITH_JQ = JQ + ["-n", "-r", "-f", os.path.join(APP_ROOT, "built_with.jq")]
RULE110_JQ = JQ + ["-n", "-r", "-f", os.path.join(APP_ROOT, "rule110.jq")]
RULE110_JQX = JQ + [
    "-r", "--rawfile", "tmpl", os.path.join(APP_ROOT, "rule110.jqx"),
    "--rawfile", "header", _EMPTY_JQX,
    "--rawfile", "head", _EMPTY_JQX,
    "--rawfile", "footer", _EMPTY_JQX,
    "-f", os.path.join(APP_ROOT, "jqx.jq"),
]
FIZZBUZZ_JQ = JQ + ["-n", "-r", "-f", os.path.join(APP_ROOT, "fizzbuzz.jq")]
FIZZBUZZ_JQX = JQ + [
    "-r", "--rawfile", "tmpl", os.path.join(APP_ROOT, "fizzbuzz.jqx"),
    "--rawfile", "header", _EMPTY_JQX,
    "--rawfile", "head", _EMPTY_JQX,
    "--rawfile", "footer", _EMPTY_JQX,
    "-f", os.path.join(APP_ROOT, "jqx.jq"),
]
PARSE_JQ = JQ + ["-f", os.path.join(APP_ROOT, "parse.jq")]
DOOM_JQ_DIR = os.path.join(APP_ROOT, "doom_jq", "jq")
DOOM_LOOP_JQ = JQ + ["-L", DOOM_JQ_DIR, "-f", os.path.join(DOOM_JQ_DIR, "loop.jq")]
DOOM_JQX = JQ + [
    "-r", "--rawfile", "tmpl", os.path.join(APP_ROOT, "doom.jqx"),
    "--rawfile", "header", _EMPTY_JQX, "--rawfile", "head", _EMPTY_JQX, "--rawfile", "footer", _EMPTY_JQX,
    "-f", os.path.join(APP_ROOT, "jqx.jq"),
]


def parse_route(method: str, path: str, body: str) -> dict:
    """Route request to action; matches parse.jq logic without subprocess."""
    p = path.split("?")[0]
    if method == "GET" and p in ("/", "/index.html"):
        return {"action": "index"}
    if method == "GET" and p == "/old":
        return {"action": "index_old"}
    if method == "GET" and p == "/built_with":
        return {"action": "built_with"}
    if method == "GET" and p == "/rule110":
        return {"action": "rule110"}
    if method == "GET" and p == "/fizzbuzz":
        return {"action": "fizzbuzz"}
    if method == "GET" and p == "/doom":
        return {"action": "doom"}
    if method == "GET" and p == "/doom/ws":
        return {"action": "doom_ws"}
    if method == "POST" and p == "/doom/tic":
        return {"action": "doom_tic", "body": body or ""}
    if method == "GET" and p == "/admin":
        return {"action": "unauthorized"}
    if method == "GET" and p == "/state":
        return {"action": "state_read"}
    if method == "GET" and p == "/favicon.ico":
        return {"action": "favicon"}
    if method == "GET" and p == "/robots.txt":
        return {"action": "robots"}
    if method == "GET" and p == "/sitemap.xml":
        return {"action": "sitemap"}
    if method == "POST" and p == "/":
        return {"action": "convert", "body": body or ""}
    if method == "POST" and p == "/state":
        return {"action": "state", "body": body or ""}
    return {"action": "not_found"}


class Handler(BaseHTTPRequestHandler):
    def parse_route(self, method: str, path: str, body: str) -> dict:
        return parse_route(method, path, body)

    def _safe_write(self, data: bytes) -> None:
        """Write response body; ignore BrokenPipeError/ConnectionResetError if client disconnected."""
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

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
        self._safe_write(body.encode("utf-8"))

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
        self._safe_write(body.encode("utf-8"))

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
        self._safe_write(body.encode("utf-8"))

    def _get_current_state(self) -> dict:
        """Return current state (e.g. from state.yml); default counter 0."""
        if not os.path.isfile(STATE_PATH):
            return {"counter": 0, "transforms": 0}
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
                return {"counter": 0, "transforms": 0}
            state = json.loads(r.stdout)
            if "counter" not in state:
                state["counter"] = 0
            if "transforms" not in state:
                state["transforms"] = 0
            return state
        except Exception:
            return {"counter": 0, "transforms": 0}

    def _doom_ws_loop(self, sock) -> None:
        """Run game loop over WebSocket: read JSON { state, input }, run jq, send JSON { state, frame }."""
        while True:
            payload = _ws_read_frame(sock)
            if payload is None:
                break
            try:
                _ = json.loads(payload)
            except json.JSONDecodeError:
                continue
            try:
                r = subprocess.run(
                    DOOM_LOOP_JQ,
                    input=payload,
                    capture_output=True,
                    text=True,
                    timeout=2,
                    cwd=APP_ROOT,
                )
                if r.returncode == 0 and r.stdout and r.stdout.strip():
                    _ws_write_frame(sock, r.stdout.strip())
            except Exception:
                break

    def do_GET(self):
        route = self.parse_route("GET", self.path, "")
        if route["action"] == "doom_ws":
            key = self.headers.get("Sec-WebSocket-Key") or self.headers.get("sec-websocket-key")
            upgrade = (self.headers.get("Upgrade") or self.headers.get("upgrade") or "").lower()
            if key and "websocket" in upgrade:
                accept = _ws_accept_key(key)
                self.send_response(101, "Switching Protocols")
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.end_headers()
                try:
                    self._doom_ws_loop(self.connection)
                except Exception:
                    pass
                return
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self._safe_write(b"Expected WebSocket upgrade")
            return
        if route["action"] == "index":
            try:
                state = self._get_current_state()
                count = state.get("counter", 0)
                transforms = state.get("transforms", 0)
                index_vars = {
                    "count": count,
                    "count_is_zero": count == 0,
                    "count_gt_0": count > 0,
                    "transforms": transforms,
                    "transforms_zero": transforms == 0,
                    "transforms_one": transforms == 1,
                    "transforms_plural": transforms != 1,
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
                    logger.error("index.jqx jq exit %s stderr: %s",
                                 r.returncode, (r.stderr or "")[:500])
                if r.returncode == 0 and (not out or not out.strip()):
                    logger.warning("index.jqx produced empty output; falling back to index.jq")
                    try:
                        r2 = subprocess.run(
                            INDEX_JQ,
                            capture_output=True,
                            text=True,
                            timeout=5,
                            cwd=APP_ROOT,
                        )
                        _log_jq_stderr(r2.stderr or "")
                        if r2.returncode == 0 and (r2.stdout or "").strip():
                            out, status = r2.stdout, 200
                        else:
                            out, status = "index.jqx produced empty output", 500
                    except Exception:
                        out, status = "index.jqx produced empty output", 500
            except Exception as e:
                logger.exception("index render failed")
                out, status = str(e), 500
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self._safe_write(out.encode("utf-8"))
        elif route["action"] == "built_with":
            try:
                state = self._get_current_state()
                count = state.get("counter", 0)
                transforms = state.get("transforms", 0)
                index_vars = {
                    "count": count,
                    "count_is_zero": count == 0,
                    "count_gt_0": count > 0,
                    "transforms": transforms,
                    "transforms_zero": transforms == 0,
                    "transforms_one": transforms == 1,
                    "transforms_plural": transforms != 1,
                }
                r = subprocess.run(
                    BUILT_WITH_JQX,
                    input=json.dumps(index_vars),
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=APP_ROOT,
                )
                _log_jq_stderr(r.stderr or "")
                out = r.stdout if r.returncode == 0 else r.stderr or "error"
                status = 200 if r.returncode == 0 else 500
                if r.returncode == 0 and (not out or not out.strip()):
                    logger.warning(
                        "built_with.jqx produced empty output; falling back to built_with.jq")
                    try:
                        r2 = subprocess.run(
                            BUILT_WITH_JQ,
                            capture_output=True,
                            text=True,
                            timeout=5,
                            cwd=APP_ROOT,
                        )
                        _log_jq_stderr(r2.stderr or "")
                        if r2.returncode == 0 and (r2.stdout or "").strip():
                            out, status = r2.stdout, 200
                        else:
                            out, status = "built_with.jqx produced empty output", 500
                    except Exception:
                        out, status = "built_with.jqx produced empty output", 500
            except Exception as e:
                logger.exception("built_with render failed")
                out, status = str(e), 500
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self._safe_write(out.encode("utf-8"))
        elif route["action"] == "rule110":
            try:
                state = self._get_current_state()
                count = state.get("counter", 0)
                query = parse_qs(urlparse(self.path).query)
                raw_gen = (query.get("generations") or [None])[0]
                try:
                    n = max(1, min(500, int(raw_gen))) if raw_gen is not None else 50
                except (TypeError, ValueError):
                    n = 50
                rule110_out = ""
                generations_used = n
                if n is not None:
                    cmd = JQ + [
                        "-n", "-r", "--argjson", "generations", str(n),
                        "--argjson", "width", "79",
                        "-f", os.path.join(APP_ROOT, "rule110.jq"),
                    ]
                    r = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        cwd=APP_ROOT,
                    )
                    _log_jq_stderr(r.stderr or "")
                    if r.returncode == 0 and r.stdout:
                        rule110_out = r.stdout
                # Pre-render counter and output block so the template needs only substitute_vars (no <If>)
                counter_html = "No visitors" if count == 0 else str(count)
                output_block = ""
                if rule110_out:
                    escaped = html_module.escape(rule110_out)
                    output_block = f'''<h2>Output</h2>
    <pre id="rule110-pre"><code id="rule110-output">{escaped}</code></pre>
    <script>
    (function() {{
      var el = document.getElementById("rule110-output");
      if (!el) return;
      var text = el.textContent;
      if (!text) return;
      var lines = text.split("\\n");
      el.textContent = "";
      var i = 0;
      function showNext() {{
        if (i < lines.length) {{
          el.textContent += (i > 0 ? "\\n" : "") + lines[i];
          i++;
          setTimeout(showNext, 150);
        }}
      }}
      setTimeout(showNext, 150);
    }})();
    </script>
    '''
                rule110_vars = {
                    "count": count,
                    "count_is_zero": count == 0,
                    "count_gt_0": count > 0,
                    "generations": generations_used,
                    "generations_display": str(generations_used) if generations_used is not None else "",
                    "output": html_module.escape(rule110_out) if rule110_out else "",
                    "has_output": bool(rule110_out),
                    "content": str(generations_used) if generations_used is not None else "",
                    "counter_html": counter_html,
                    "output_block": output_block,
                }
                r = subprocess.run(
                    RULE110_JQX,
                    input=json.dumps(rule110_vars),
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=APP_ROOT,
                )
                _log_jq_stderr(r.stderr or "")
                out = r.stdout if r.returncode == 0 else r.stderr or "error"
                status = 200 if r.returncode == 0 else 500
            except Exception as e:
                logger.exception("rule110 failed")
                out, status = str(e), 500
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self._safe_write(out.encode("utf-8"))
        elif route["action"] == "doom":
            try:
                state = self._get_current_state()
                count = state.get("counter", 0)
                counter_html = "No visitors" if count == 0 else str(count)
                # Inline script: game loop over WebSocket /doom/ws (one connection, stream tics). Break </script> so parser does not close early.
                doom_script = (
                    "<script>\n"
                    "(function() {\n"
                    "  var canvas = document.getElementById('doom-canvas');\n"
                    "  if (!canvas) return;\n"
                    "  var ctx = canvas.getContext('2d');\n"
                    "  var keys = new Set();\n"
                    "  var keyToName = { ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right', KeyW: 'Up', KeyS: 'Down', KeyA: 'Left', KeyD: 'Right' };\n"
                    "  function onKey(e, add) {\n"
                    "    var name = keyToName[e.code];\n"
                    "    if (name) { e.preventDefault(); if (add) keys.add(name); else keys.remove(name); }\n"
                    "  }\n"
                    "  document.addEventListener('keydown', function(e) { onKey(e, true); });\n"
                    "  document.addEventListener('keyup', function(e) { onKey(e, false); });\n"
                    "  var gameState = null;\n"
                    "  var pending = false;\n"
                    "  function drawFrame(frame) {\n"
                    "    if (!frame || !frame.draw) return;\n"
                    "    var w = frame.width || 320, h = frame.height || 200;\n"
                    "    ctx.fillStyle = '#000';\n"
                    "    ctx.fillRect(0, 0, w, h);\n"
                    "    for (var i = 0; i < frame.draw.length; i++) {\n"
                    "      var d = frame.draw[i];\n"
                    "      ctx.fillStyle = d.color || '#333';\n"
                    "      var r = d.rect;\n"
                    "      if (r && r.length >= 4) ctx.fillRect(r[0], r[1], r[2], r[3]);\n"
                    "    }\n"
                    "  }\n"
                    "  var wsUrl = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/doom/ws';\n"
                    "  var ws = new WebSocket(wsUrl);\n"
                    "  function tick() {\n"
                    "    if (!ws || ws.readyState !== WebSocket.OPEN || pending) { requestAnimationFrame(tick); return; }\n"
                    "    pending = true;\n"
                    "    ws.send(JSON.stringify({ state: gameState, input: { keys: Array.from(keys) } }));\n"
                    "  }\n"
                    "  ws.onmessage = function(e) {\n"
                    "    pending = false;\n"
                    "    try {\n"
                    "      var data = JSON.parse(e.data);\n"
                    "      gameState = data.state;\n"
                    "      if (data.frame) drawFrame(data.frame);\n"
                    "    } catch (err) {}\n"
                    "    requestAnimationFrame(tick);\n"
                    "  };\n"
                    "  ws.onerror = ws.onclose = function() { pending = false; };\n"
                    "  ws.onopen = function() { requestAnimationFrame(tick); };\n"
                    "})();\n"
                    "</scr" + "ipt>\n"
                )
                doom_vars = {"counter_html": counter_html, "doom_script": doom_script}
                r = subprocess.run(
                    DOOM_JQX,
                    input=json.dumps(doom_vars),
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=APP_ROOT,
                )
                _log_jq_stderr(r.stderr or "")
                out = r.stdout if r.returncode == 0 else r.stderr or "error"
                status = 200 if r.returncode == 0 else 500
            except Exception as e:
                logger.exception("doom page failed")
                out, status = str(e), 500
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self._safe_write(out.encode("utf-8"))
        elif route["action"] == "fizzbuzz":
            try:
                state = self._get_current_state()
                count = state.get("counter", 0)
                query = parse_qs(urlparse(self.path).query)
                raw_n = (query.get("n") or [None])[0]
                try:
                    n = max(1, min(500, int(raw_n))) if raw_n is not None else 30
                except (TypeError, ValueError):
                    n = 30
                n_used = n
                run_requested = raw_n is not None
                fizzbuzz_out = ""
                if run_requested:
                    cmd = JQ + [
                        "-n", "-r", "--argjson", "n", str(n),
                        "-f", os.path.join(APP_ROOT, "fizzbuzz.jq"),
                    ]
                    r = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        cwd=APP_ROOT,
                    )
                    _log_jq_stderr(r.stderr or "")
                    if r.returncode == 0 and r.stdout:
                        fizzbuzz_out = r.stdout
                counter_html = "No visitors" if count == 0 else str(count)
                output_block = ""
                if fizzbuzz_out:
                    escaped = html_module.escape(fizzbuzz_out)
                    output_block = f'''<h2>Output</h2>
    <pre id="fizzbuzz-pre"><code id="fizzbuzz-output">{escaped}</code></pre>
    '''
                code_snippet = ""
                try:
                    with open(os.path.join(APP_ROOT, "fizzbuzz.jq"), encoding="utf-8") as f:
                        code_snippet = html_module.escape(f.read())
                except OSError:
                    code_snippet = "(fizzbuzz.jq not found)"
                fizzbuzz_vars = {
                    "count": count,
                    "count_is_zero": count == 0,
                    "count_gt_0": count > 0,
                    "n": n_used,
                    "n_display": str(n_used),
                    "output": html_module.escape(fizzbuzz_out) if fizzbuzz_out else "",
                    "has_output": bool(fizzbuzz_out),
                    "counter_html": counter_html,
                    "output_block": output_block,
                    "code_snippet": code_snippet,
                }
                r = subprocess.run(
                    FIZZBUZZ_JQX,
                    input=json.dumps(fizzbuzz_vars),
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=APP_ROOT,
                )
                _log_jq_stderr(r.stderr or "")
                out = r.stdout if r.returncode == 0 else r.stderr or "error"
                status = 200 if r.returncode == 0 else 500
            except Exception as e:
                logger.exception("fizzbuzz failed")
                out, status = str(e), 500
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self._safe_write(out.encode("utf-8"))
        elif route["action"] == "index_old":
            try:
                r = subprocess.run(INDEX_OLD_JQ, capture_output=True,
                                   text=True, timeout=5, cwd=APP_ROOT)
                _log_jq_stderr(r.stderr or "")
                out = r.stdout if r.returncode == 0 else r.stderr or "error"
                status = 200 if r.returncode == 0 else 500
            except Exception as e:
                logger.exception("index_old failed")
                out, status = str(e), 500
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self._safe_write(out.encode("utf-8"))
        elif route["action"] == "unauthorized":
            self.send_401()
        elif route["action"] == "state_read":
            try:
                state = self._get_current_state()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self._safe_write(json.dumps(state).encode())
            except Exception as e:
                logger.exception("GET /state failed")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self._safe_write(json.dumps({"message": str(e)}).encode())
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
                self._safe_write(data)
            else:
                self.send_404()
        elif route["action"] == "robots":
            data = _robots_txt().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self._safe_write(data)
        elif route["action"] == "sitemap":
            data = _sitemap_xml().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self._safe_write(data)
        else:
            self.send_404()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_SIZE:
            logger.warning("body size %s exceeds limit %s", length, MAX_BODY_SIZE)
            self.send_response(413)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self._safe_write(json.dumps({"message": "Request entity too large"}).encode())
            return
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        route = self.parse_route("POST", self.path, body)
        if route["action"] == "doom_tic":
            try:
                payload = route.get("body", "{}").strip() or "{}"
                r = subprocess.run(
                    DOOM_LOOP_JQ,
                    input=payload,
                    capture_output=True,
                    text=True,
                    timeout=2,
                    cwd=APP_ROOT,
                )
                _log_jq_stderr(r.stderr or "")
                if r.returncode != 0:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self._safe_write(json.dumps({"error": r.stderr or "jq failed"}).encode())
                    return
                out = r.stdout.strip()
                if not out:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self._safe_write(json.dumps({"error": "empty jq output"}).encode())
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self._safe_write(out.encode("utf-8"))
            except subprocess.TimeoutExpired:
                logger.error("POST /doom/tic timeout")
                self.send_response(408)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self._safe_write(json.dumps({"error": "timeout"}).encode())
            except Exception as e:
                logger.exception("POST /doom/tic failed")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self._safe_write(json.dumps({"error": str(e)}).encode())
        elif route["action"] == "convert":
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
            self._safe_write(out.encode("utf-8"))
            if status == 200:
                try:
                    with _state_lock:
                        state = self._get_current_state()
                        state["transforms"] = state.get("transforms", 0) + 1
                        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
                        with open(STATE_PATH, "w") as f:
                            yaml.dump(state, f, default_flow_style=False, sort_keys=False)
                except Exception:
                    logger.exception("failed to increment transforms in state")
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
                        current_state = {"counter": 0, "transforms": 0}
                    if "counter" not in current_state:
                        current_state["counter"] = 0
                    if "transforms" not in current_state:
                        current_state["transforms"] = 0
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
                        self._safe_write(json.dumps(
                            {"message": r.stderr or "state.jq failed"}).encode())
                        return
                    result = json.loads(r.stdout)
                    if result.get("valid"):
                        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
                        with open(STATE_PATH, "w") as f:
                            yaml.dump(result["new_state"], f,
                                      default_flow_style=False, sort_keys=False)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self._safe_write(json.dumps(result["new_state"]).encode())
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
                self._safe_write(json.dumps({"message": str(e)}).encode())
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
