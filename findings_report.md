# jqyml — Code Review Findings Report

**Date:** 2026-02-21
**Reviewer:** Senior jq/jqx Engineer
**Scope:** Full codebase review — `yaml.jq`, `jqx.jq`, `server.py`, `parse.jq`, `state.jq`, templates, Dockerfile, Makefile, test suite
**Last updated:** 2026-02-21 (post-fix iteration)

---

## Executive Summary

The project is a YAML-to-JSON HTTP service built on an unconventional stack: a pure-jq YAML parser (`yaml.jq`) serving as the backend logic, a minimal Python HTTP server (`server.py`), and a lightweight jq-based template engine (`jqx.jq`). All tests pass green. The architecture is coherent and the code is generally readable.

**All HIGH, MEDIUM, and LOW items from this report have been addressed.** M5 (fallback removed, 500 on empty jqx), L4 (ownership comments), L5 (GET /old documented), and L8 (trailing-blank trim, single clip-newline) are resolved.

---

## HIGH Priority

### ✅ H1 — YAML merge key `<<` is silently ignored *(RESOLVED)*

**Fix:** `detect_line_type` in `yaml.jq:131` changed from `^[a-zA-Z0-9_-]+:` to `^[^:]+:` and now also explicitly handles `startswith("<<:")`. The `<<` merge key is correctly classified as `key_value` and handled by the existing merge logic in `_process_line`.

**Verified by:** `tests/anchors/03_merge.yaml`, `07_complex_merge.yaml`, `08_merge_override_priority.yaml`, `tests/14_anchors_used.yaml` all pass with correct merged output.

---

### ✅ H2 — Anchor/merge test expectations reflect the bug, not correct behavior *(RESOLVED)*

**Fix:** All merge-related `.expected` files corrected:
- `tests/anchors/03_merge.expected` updated (`extended` now includes merged field `a: 1`)
- `tests/anchors/07_complex_merge.expected` updated (merged fields appear in `service_a` and `service_b`)
- `tests/14_anchors_used.expected` added (was smoke-test only; now has output comparison)
- New test `tests/anchors/08_merge_override_priority.yaml` added to guard against regression

---

### ✅ H3 — Nested `<If>` blocks in jqx produce wrong output *(RESOLVED)*

**Fix:** `jqx.jq` now implements `find_matching_endif($s; $from)` — a recursive, balanced-tag finder that correctly locates the `</If>` that pairs with the current opening `<If>`, skipping over any nested `<If>` blocks. `expand_one_if` now calls this instead of using a greedy `index("</If>")`.

**Verified by:** `tests/jqx/11_nested_if.jqx` (`a=true, b=false`) and `tests/jqx/12_nested_if_both_true.jqx` both pass with correct output (`outerrest` and `outerinnerrest` respectively).

---

## MEDIUM Priority

### ✅ M1 — No request body size limit *(RESOLVED)*

**Fix:** `server.py:15` adds `MAX_BODY_SIZE = 1_000_000`. In `do_POST`, any request with `Content-Length > MAX_BODY_SIZE` is rejected immediately with HTTP 413 and a warning log entry — before reading the body. Logged at `logger.warning`.

**Verified by:** `make test-server` exercises the 413 path with a 1 MB + 1 byte payload.

---

### ✅ M2 — Race condition on state read/write *(RESOLVED)*

**Fix:** `server.py:18` introduces `_state_lock = threading.Lock()` (module-level). The state read-modify-write block in `do_POST` is now wrapped with `with _state_lock:`, preventing concurrent increments from losing updates.

---

### ✅ M3 — Quoted YAML strings containing JSON are silently coerced *(RESOLVED)*

**Fix:** `yaml.jq:100` in `coerce_value` now short-circuits for `quoted_string` type:

```jq
| if $t == "quoted_string" then $result
  elif ($result | type) == "string" then $result | try_parse_json
  else $result end
```

Quoted strings are returned as-is after unquoting, without the subsequent JSON re-parse. Unquoted strings that look like JSON (e.g., bare `[1,2,3]`) are still coerced.

**Verified by:** `tests/19_quoted_json_string.yaml` passes with `{"array_str":"[1,2,3]","object_str":"{\"a\":1}"}`.

---

### ✅ M4 — All logging suppressed in production *(RESOLVED)*

**Fix:** `server.py` now uses Python's `logging` module fully:
- `logging.basicConfig(level=logging.INFO)` configured at startup
- `logger = logging.getLogger("jqyml")` used throughout
- `log_message` now calls `logger.info(format % args)` instead of `pass`
- All subprocess failures, 413s, timeouts, and exceptions logged at appropriate levels (`logger.error`, `logger.exception`, `logger.warning`)
- jq stderr forwarded to Python logging via a `_forward_jq_stderr` helper

---

### ✅ M5 — Silent fallback from `index.jqx` to `index.jq` *(RESOLVED)*

**Fix:** The fallback to `index.jq` was removed. When `index.jqx` produces empty output (exit 0), the server now logs `logger.error("index.jqx produced empty output; returning 500")` and returns HTTP 500 with body `"index.jqx produced empty output"`. Regressions in the jqx template are now visible immediately.

---

### ✅ M6 — Error page variable naming inconsistent across templates *(RESOLVED)*

**Fix:** `404.jqx` changed from `{error_code}` to `{status}` throughout. `NOT_FOUND_VARS` in `server.py:50` updated to use `"status"` as the key. All three error page templates (`400.jqx`, `401.jqx`, `404.jqx`) now uniformly use `{status}` as the HTTP status code placeholder.

**Note:** `tests/jqx/06_404.jqx` was updated to use `{status}` so it mirrors production `404.jqx`. Tests `13_400_error_page` and `14_401_error_page` exercise the 400/401 templates with `{status}`.

---

### ✅ M7 — No `.gitignore` *(RESOLVED)*

**Fix:** `.gitignore` added at project root covering:
- `__pycache__/`, `*.py[cod]`, `*.so` — Python build artifacts
- `*.swp`, `*.swo`, `.DS_Store` — editor and OS noise
- `*.log` — log files
- `state/state.yml` — runtime state (correctly excluded; the image seeds an initial `counter: 0`)

---

## LOW Priority

### ✅ L1 — YAML keys with spaces are silently dropped *(RESOLVED)*

**Fix:** Same regex change as H1 — `detect_line_type` now uses `^[^:]+:` which matches any key not containing a literal colon, including keys with spaces, hyphens beyond `[a-z0-9]`, and other previously-excluded characters.

**Verified by:** `tests/20_keys_with_spaces.yaml` passes with `{"my key":"value","another key":42}`.

---

### ✅ L2 — `parse_route` spawns a `jq` subprocess on every request *(RESOLVED)*

**Fix:** `parse_route` is now a pure Python function in `server.py:86–101`. It replicates the `parse.jq` if/elif routing logic in native Python with no subprocess. The `PARSE_JQ` constant is retained for reference but is no longer called. Every request saves a full `jq` process-spawn round-trip.

---

### ✅ L3 — `GET /state` route has no test coverage *(RESOLVED)*

**Fix:** `make test-server` (added to `Makefile:88–109`) starts the server on `TEST_PORT`, issues a live `GET /state`, and asserts HTTP 200 with a body containing `"counter"`. Also covers the 413 body-size limit and 404 for unknown routes.

---

### ✅ L4 — `index.jq` and `index.jqx` have diverged without a clear ownership model *(RESOLVED)*

**Fix:** Comment blocks were added at the top of both files. `index.jq` states it is static, used only for local `make run`; production serves `index.jqx`; there is no fallback (empty jqx → 500). `index.jqx` states it is the production front page (jqx + counter + conditionals) and that empty output results in HTTP 500. The fallback was removed (M5), so `index.jq` is no longer served on empty jqx.

---

### ✅ L5 — `/old` route serves an undocumented dead-end *(RESOLVED)*

**Fix:** Documented in `features.md` under Server & API: `GET /old` serves a minimal, unstyled YAML→JSON converter (no counter, no CSS) for low-bandwidth or legacy clients; route kept for compatibility. `parse.jq` already had an inline comment describing the route.

---

### ✅ L6 — No Docker health check *(RESOLVED)*

**Fix:** `docker-compose.yml` now defines a `healthcheck` on the `jqyml` service:

```yaml
healthcheck:
  test: ["CMD", "wget", "-q", "--spider", "http://localhost:8888/"]
  interval: 5s
  timeout: 3s
  retries: 3
  start_period: 5s
```

Caddy's `depends_on` now uses `condition: service_healthy`, ensuring Caddy does not begin proxying until jqyml is confirmed ready.

---

### ✅ L7 — `state.yml` resets on container restart *(RESOLVED)*

**Fix:** `docker-compose.yml` mounts a named volume:

```yaml
jqyml:
  volumes:
    - jqyml_state:/app/state
volumes:
  jqyml_state:
```

The `state/` directory is now backed by a persistent Docker volume. Counter state survives container restarts and image rebuilds. The `COPY state/ /app/state/` in the Dockerfile still provides the initial seed (`counter: 0`) on first volume creation.

---

### ✅ L8 — Block scalar trailing newline overcorrection *(RESOLVED)*

**Fix:** Added `_trim_trailing_blanks` in `yaml.jq`: it recursively drops trailing entries in the block scalar `lines` array where `.blank` is true, so the separator blank line before the next key is not included in the scalar content. `_block_build_string` now builds from the trimmed lines and appends exactly one `"\n"` (YAML clip-chomping). Literal and folded block scalars now produce a single trailing newline. `tests/18_block_scalars.expected` and `tests/21_block_scalar_last_key.expected` were updated to the spec-correct output.

---

## Test Coverage Summary

| Area | Tests | Coverage |
|---|---|---|
| YAML parser (smoke + output) | 21 YAML files; 7 with `.expected` output comparison | Good; edge cases for spaces, quoted JSON, block scalars covered |
| Anchor/alias/merge | 8 `.expected` comparisons | Solid; scalar, block, merge, multi-anchor, nested, override all covered |
| jqx template engine | 14 `.expected` comparisons | Good; `<If>`, nested `<If>`, `<For>`, missing vars, all 3 error pages covered |
| state.jq logic | 6 `.expected` + 1 parse test | Solid |
| Server integration | `make test-server` (live HTTP) | 413 body limit, 404, GET /state verified |
| Speed regression | `make test-speed` (50 iterations) | ~36ms/run baseline established |

---

## Summary Table

| ID | Severity | Status | Description |
|---|---|---|---|
| H1 | HIGH | ✅ Resolved | `<<` merge key — regex widened to `^[^:]+:` + explicit `startswith("<<:")` |
| H2 | HIGH | ✅ Resolved | Merge `.expected` files corrected; `14_anchors_used.expected` added |
| H3 | HIGH | ✅ Resolved | Nested `<If>` — `find_matching_endif` recursive balanced-tag finder added |
| M1 | MED | ✅ Resolved | `MAX_BODY_SIZE = 1_000_000`; 413 returned and logged; `test-server` covers it |
| M2 | MED | ✅ Resolved | `threading.Lock()` wraps state read-modify-write |
| M3 | MED | ✅ Resolved | `coerce_value` skips `try_parse_json` for `quoted_string` type |
| M4 | MED | ✅ Resolved | Full `logging` module; `log_message` forwards; jq stderr bridged |
| M5 | MED | ✅ Resolved | Fallback removed; empty jqx → HTTP 500 and error log |
| M6 | MED | ✅ Resolved | All error templates standardised on `{status}`; `NOT_FOUND_VARS` updated |
| M7 | MED | ✅ Resolved | `.gitignore` added covering pycache, editors, logs, runtime state |
| L1 | LOW | ✅ Resolved | Keys with spaces — same regex fix as H1 |
| L2 | LOW | ✅ Resolved | `parse_route` inlined as pure Python; no subprocess per request |
| L3 | LOW | ✅ Resolved | `make test-server` exercises `GET /state` live |
| L4 | LOW | ✅ Resolved | Comment blocks in both index files; fallback removed (M5) |
| L5 | LOW | ✅ Resolved | GET /old documented in features.md; parse.jq comment |
| L6 | LOW | ✅ Resolved | Docker healthcheck added; Caddy uses `condition: service_healthy` |
| L7 | LOW | ✅ Resolved | Named volume `jqyml_state` persists counter across restarts |
| L8 | LOW | ✅ Resolved | `_trim_trailing_blanks` + single `\n`; expected files updated |
