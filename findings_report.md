# jqyml — Code Review Findings Report

**Date:** 2026-02-21
**Reviewer:** Senior jq/jqx Engineer
**Scope:** Full codebase review — `yaml.jq`, `jqx.jq`, `server.py`, `parse.jq`, `state.jq`, templates, Dockerfile, Makefile, test suite

---

## Executive Summary

The project is a YAML-to-JSON HTTP service built on an unconventional stack: a pure-jq YAML parser (`yaml.jq`) serving as the backend logic, a minimal Python HTTP server (`server.py`), and a lightweight jq-based template engine (`jqx.jq`). All tests pass green. The architecture is coherent and the code is generally readable.

Two critical correctness bugs exist — one that silently breaks YAML merge keys and one that causes incorrect jqx template rendering for nested conditionals. Additionally, there are several medium and low priority issues around robustness, security, test coverage, and developer hygiene.

---

## HIGH Priority

### H1 — YAML merge key `<<` is silently ignored (yaml.jq)

**File:** `yaml.jq:127`
**Impact:** Correctness — merge keys are a core YAML 1.1 feature

`detect_line_type` classifies lines using:
```jq
elif ($stripped | test("^[a-zA-Z0-9_-]+:\\s*.+")) then "key_value"
```

The character class `[a-zA-Z0-9_-]` does **not** include `<`. Therefore `<<: *anchor` does not match and falls through to `"scalar"`, which `_process_line` ignores silently (the `else .` branch).

**Demonstrated:**
```yaml
defaults: &defaults
  host: localhost
  port: 80
dev:
  <<: *defaults   # silently skipped
  port: 8080
```
**Actual output:** `{"dev":{"port":8080}}`
**Expected output:** `{"dev":{"host":"localhost","port":8080}}`

The fix is to extend the detection regex to also match `<<:`:
```jq
elif ($stripped | startswith("<<:") or test("^[a-zA-Z0-9_-]+:\\s*.+")) then "key_value"
```
The downstream `key_value_line_handler` already correctly handles the `<<` key, and the alias/merge logic in `_process_line` is in place — this is purely a classification miss.

---

### H2 — Anchor/merge test expectations reflect the bug, not correct behavior

**File:** `tests/anchors/07_complex_merge.expected`, `tests/14_anchors_used.yaml`
**Impact:** The test suite passes but masks the H1 bug

`tests/anchors/07_complex_merge.expected` expects:
```json
{"common":{"env":"shared","debug":false},"service_a":{"name":"A"},"service_b":{"name":"B","debug":true}}
```

Correct YAML behavior would be:
```json
{"common":{"env":"shared","debug":false},"service_a":{"env":"shared","debug":false,"name":"A"},"service_b":{"env":"shared","debug":true,"name":"B"}}
```

The `.expected` file was generated from the broken implementation. Once H1 is fixed, all merge-related `.expected` files need updating. Similarly, `tests/14_anchors_used.yaml` is only smoke-tested (exit code check), with no `.expected` comparison; the merged fields would never be verified.

---

### H3 — Nested `<If>` blocks in jqx produce wrong output (jqx.jq)

**File:** `jqx.jq:8–27`
**Impact:** Correctness — content outside an inner `<If>` but inside an outer `<If>` is lost when the inner condition is false

`expand_one_if` uses `index("</If>")` to find the closing tag, which always finds the **first** `</If>` in the string, not the one matching the current opening tag. With nested `<If>`:

```
<If a>outer<If b>inner</If>rest</If>
```

When `a=true, b=false`:
- First pass expands `<If a>` with content = `outer<If b>inner` (stops at first `</If>`), after = `rest</If>`
- Result: `outer<If b>innerrest</If>`
- Second pass: `<If b>` false, so content `innerrest` is dropped
- Final result: `outer`  ← **`rest` is lost**

Expected result: `outerrest`

This is a fundamental limitation of the greedy single-pass `index("</If>")` approach. Fixing it requires either a recursive balanced-tag finder or a convention prohibiting nested `<If>` blocks (which should be documented clearly if not fixed).

---

## MEDIUM Priority

### M1 — No request body size limit (server.py)

**File:** `server.py:193–194`

```python
length = int(self.headers.get("Content-Length", 0))
body = self.rfile.read(length).decode("utf-8", errors="replace")
```

There is no cap on `Content-Length`. A client can send a multi-gigabyte YAML payload, which will be held in memory and then passed to `jq` as a subprocess input. The `jq` process also has a 10-second timeout (`POST /`), but by then the server may already be OOM. A simple guard (e.g., reject if `length > 1_000_000`) would prevent this.

---

### M2 — Race condition on state read/write (server.py)

**File:** `server.py:222–266`

The `POST /state` handler reads `state.yml`, increments the counter, and writes it back — all without any file locking. Under concurrent requests (unlikely at current traffic but not impossible), two requests can both read `counter: 5` and both write `counter: 6`, losing an increment. Python's `threading.Lock` or `fcntl.flock` would resolve this.

---

### M3 — Quoted YAML strings containing JSON are silently coerced (yaml.jq)

**File:** `yaml.jq:88–100`

`coerce_value` first unquotes a YAML quoted string, then calls `try_parse_json` on the result:

```jq
| if ($result | type) == "string" then $result | try_parse_json else $result end
```

So `key: "[1,2,3]"` (explicitly quoted string in YAML) is parsed and emitted as a JSON array `[1,2,3]` instead of the string `"[1,2,3]"`. In standard YAML, quoting a value forces it to be a string. This type mutation could cause silent data corruption for applications relying on string values that happen to contain valid JSON.

---

### M4 — All logging suppressed in production (server.py)

**File:** `server.py:286–287`

```python
def log_message(self, format, *args):
    pass
```

Every request is silently swallowed. There is no error logging, no access logging, and no way to diagnose issues in production (e.g., jq parse failures, subprocess timeouts). At minimum, errors (5xx responses, subprocess failures) should be logged to stderr.

---

### M5 — Silent fallback from `index.jqx` to `index.jq` (server.py)

**File:** `server.py:148–157`

```python
if r.returncode == 0 and (not out or not out.strip()):
    r = subprocess.run(INDEX_JQ, ...)
```

If the jqx template engine produces empty output (but exits 0), the server silently renders the static `index.jq` instead. The static version does not include the visitor counter or the conditional rendering. This fallback is invisible to the operator and the user, and would make template regressions very hard to notice. The fallback should either be removed (fail loudly) or logged.

---

### M6 — Error page variable naming inconsistent across templates

**Files:** `404.jqx`, `400.jqx`, `401.jqx`

`404.jqx` uses `{error_code}` as the HTTP status placeholder; `400.jqx` and `401.jqx` use `{status}`. These are the same semantic concept with different names. If a new error template is added, the correct variable name is ambiguous. Standardize on one name (e.g., `{status}`) across all error templates.

---

### M7 — No `.gitignore` — `__pycache__` is untracked noise

**Files:** project root (missing `.gitignore`)

`__pycache__/` appears as untracked in `git status`. There is no `.gitignore` in the repo. This should be added to prevent build artifacts, editor files, and Python bytecode from cluttering `git status` and accidentally being staged.

---

## LOW Priority

### L1 — YAML keys with spaces are silently dropped (yaml.jq)

**File:** `yaml.jq:127`

`detect_line_type` matches keys with `^[a-zA-Z0-9_-]+:`. A key like `my key: value` (space in key) does not match any pattern and is classified as "scalar", then silently ignored. The output is `{}`. Standard YAML allows unquoted keys with spaces. This is a known parser limitation but is not documented anywhere, and silent data loss is worse than a clear error.

---

### L2 — `parse_route` is a subprocess call on every request (server.py)

**File:** `server.py:35–46`

```python
r = subprocess.run(PARSE_JQ, input=json.dumps(request), ...)
```

`parse.jq` contains simple if/elif routing logic. Spawning a `jq` subprocess for every single request (including every YAML conversion) adds ~10–30ms of process-spawn overhead per request plus the cost of jq startup. Since routing logic is static and simple, it could be inlined into Python with zero overhead. This is the single easiest performance win available.

---

### L3 — `GET /state` is untested (Makefile / tests)

**File:** `Makefile`, `tests/state/`

The `state.jq` tests cover `POST /state` scenarios. The `GET /state` route (which returns the current state JSON) has no dedicated test. It delegates to `_get_current_state()` which reads `state.yml` via `run.jq`. If `state.yml` is missing or malformed, the fallback `{"counter": 0}` is returned silently. A test covering this path (including the missing-file case) would improve confidence.

---

### L4 — `index.jq` and `index.jqx` have diverged without a clear ownership model

**Files:** `index.jq`, `index.jqx`

`index.jqx` is the active template (served via jqx engine with conditional visitor count logic). `index.jq` is the static fallback and is also referenced in the Makefile `run` target. The two files have diverged: `index.jqx` has the correct `showCount` JS logic with `n === 0 ? "No visitors" : n`, while `index.jq` does not. If someone edits `index.jq` thinking it's the primary file, changes won't appear in production. Consider removing `index.jq` as a served route and keeping it only as a documented fallback, or delete it entirely.

---

### L5 — `/old` route serves a permanently maintained dead-end page

**File:** `index_old.jq`, `parse.jq:8`, `server.py:164`

`GET /old` serves a styled-free version of the converter with no visitor counter. There's no indication in the UI or docs what "old" means or why it exists. If this is a migration artifact, it should be removed. If it's intentional (e.g., for low-bandwidth clients), it should be documented.

---

### L6 — No Docker health check; Caddy may route before jqyml is ready

**File:** `docker-compose.yml`

```yaml
depends_on:
  - jqyml
```

`depends_on` only waits for the container to start, not for the HTTP server inside it to be listening. Under load or slow machines, Caddy may start routing to `jqyml:8888` before Python's `HTTPServer.serve_forever()` is ready. A `healthcheck` on the jqyml service would eliminate this race.

---

### L7 — `state.yml` is COPY'd into the Docker image

**File:** `Dockerfile:5`

```
COPY state/ /app/state/
```

The initial `state/state.yml` (`counter: 0`) is baked into the image. On container restart, the counter resets to whatever was in the image layer (0), not what was written at runtime. For the counter to survive restarts, `state/` needs to be a Docker volume mount. This is likely intentional for now but is a latent confusion for operators.

---

### L8 — `block_scalar` folded mode trailing newline handling may surprise

**File:** `yaml.jq:196–204`

The `_block_build_string` implementation for folded scalars (`>`) joins non-blank lines with a space and blank lines with `\n`. Standard YAML folded scalars append a trailing newline. The current implementation does not explicitly add one. In practice the trailing newline comes from the blank line separator, but edge cases (folded block as the last key with no trailing blank line) may not produce the expected trailing newline. This was not caught by the existing `18_block_scalars.yaml` tests.

---

## Test Coverage Summary

| Area | Tests | Coverage |
|---|---|---|
| YAML parser (smoke) | 18 YAML files, exit-code only | No output comparison |
| Anchor/alias/merge | 7 `.expected` comparisons | H2: merge expectations are wrong |
| jqx template engine | 10 `.expected` comparisons | Nested `<If>` not covered |
| state.jq logic | 6 `.expected` + 1 parse test | Solid |
| `GET /state` route | None | Gap |
| YAML edge cases (keys w/ spaces, tabs, multiline) | None | Gap |

---

## Summary Table

| ID | Severity | File(s) | Description |
|---|---|---|---|
| H1 | HIGH | `yaml.jq:127` | `<<` merge key silently ignored — not matched by line-type regex |
| H2 | HIGH | `tests/anchors/*.expected` | Test expectations reflect broken behavior, not correct YAML |
| H3 | HIGH | `jqx.jq:8–27` | Nested `<If>` blocks drop outer content when inner condition is false |
| M1 | MED | `server.py:193` | No POST body size limit — unbounded memory use |
| M2 | MED | `server.py:222–266` | State read/write has no file lock — race condition under concurrency |
| M3 | MED | `yaml.jq:88–100` | Quoted YAML strings containing JSON are coerced to JSON types |
| M4 | MED | `server.py:286` | All logging suppressed — no observability in production |
| M5 | MED | `server.py:148–157` | Silent fallback from jqx to static index.jq on empty template output |
| M6 | MED | `400.jqx`, `404.jqx`, `401.jqx` | Error page status variable named inconsistently (`{status}` vs `{error_code}`) |
| M7 | MED | project root | No `.gitignore` — `__pycache__` and build artifacts accumulate |
| L1 | LOW | `yaml.jq:127` | Keys with spaces silently dropped instead of erroring |
| L2 | LOW | `server.py:35` | Route parsing spawns a `jq` subprocess per request — trivially avoidable overhead |
| L3 | LOW | `tests/` | `GET /state` route has no test coverage |
| L4 | LOW | `index.jq`, `index.jqx` | Two diverged index templates — unclear ownership, confusing fallback |
| L5 | LOW | `index_old.jq`, `parse.jq` | `/old` route is an undocumented dead-end |
| L6 | LOW | `docker-compose.yml` | No health check — Caddy may proxy before jqyml is listening |
| L7 | LOW | `Dockerfile`, `docker-compose.yml` | `state/` not volume-mounted — counter resets on container restart |
| L8 | LOW | `yaml.jq:196–204` | Folded block scalar trailing newline edge case not verified |
