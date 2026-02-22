# Potential features

Ideas for future work on jqyml. Not a roadmap—pick what fits.

---

## Logging (implemented)

**`log.jq`** provides a log/slog-style API for the jq engine:

- **`log($msg)`** – Writes a simple message to stderr (via jq’s `debug`) and passes the current value through. Use in a pipeline: `... | log("step 1") | ...`
- **`slog($level; $msg)`** – Structured log with level (e.g. `"info"`, `"warn"`, `"error"`) and message; emits a single JSON object to stderr.
- **`slog($level; $msg; $attrs)`** – Same, plus key-value attributes (object). Example: `slog("info"; "parsing"; {"path": $path})`

**Usage:** In any jq script that runs with `-L /app` (or `-L .`), add `include "log";` then call `log(...)` or `slog(...)` in the pipeline. The input value is unchanged so logging is side-effect only.

**Stderr format:** jq’s `debug` prefixes each line with `["DEBUG:", "<content>"]`. For `slog`, `<content>` is a JSON string of `{level, msg, ...attrs}`. To use from the server: capture stderr in `subprocess.run(..., capture_output=True)` and either forward it (e.g. to the app logger) or parse lines and log with a real logger.

---

## YAML parsing (yaml.jq / run.jq)

- **Merge key (`<<: *anchor`)** – Apply merged keys into the target object so `dev: { <<: *defaults, port: 8080 }` yields `{ host: "localhost", port: 8080 }` (currently only local keys are kept).
- **Multi-document** – Support `---` document separators and return an array of parsed documents or stream.
- **Flow collections** – Inline `{ key: value }` and `[ a, b ]` in the parser (not only embedded JSON).
- **Tags and types** – Optional handling of `!!str`, `!!int`, etc., or explicit typing hints.
- **Stricter spec** – Reject or define behaviour for ambiguous cases (e.g. duplicate keys, key order).
- **YAML 1.2** – Align with 1.2 spec where it diverges from current behaviour.

---

## jqx templating

- **Large templates** – Avoid jq stack overflow on big templates (e.g. index.jqx): iterative expansion or chunked processing so the main page always renders without falling back to index.jq.
- **`<If not name>` or `<Else>`** – Negation or else branch for conditionals.
- **Nested / repeated conditionals** – Clear semantics and tests for `<If>` inside `<For>` or multiple `<If>` in a row.
- **Partials / includes** – e.g. `<Include name>` to pull in another template fragment.
- **Escaping** – Delimiters for literal `{var}` or `<If` in content (e.g. `\{var}` or `<If raw>`).
- **Expression in `<If>`** – e.g. `<If count==0>` or `<If count gt 0>` instead of precomputed booleans.

---

## Server & API

- **GET /state** – Already present; consider ETag/Last-Modified or short caching for the counter.
- **Health/readiness** – e.g. `GET /health` or `GET /ready` for orchestration.
- **Request size limit** – Cap POST body length to avoid abuse.
- **Rate limiting** – Throttle by IP or path (e.g. POST /state) to protect the service.
- **Structured logging** – Log method, path, status, duration; optional request IDs.
- **Config file** – Port, paths, feature flags (e.g. enable/disable state) without code changes.
- **CORS** – Configurable `Access-Control-*` headers for browser clients.

---

## State engine

- **Richer state** – More than `counter` (e.g. last_visit, user_prefs) with validation in state.jq.
- **Persistence options** – Besides a single YAML file, optional SQLite or external store.
- **Reset / admin** – Authenticated or token-protected endpoint to reset or inspect state.
- **Audit** – Append-only log of state changes (who/what/when) for debugging or compliance.

---

## UI / UX

- **Copy result** – One-click copy of converted JSON (or “Copied” feedback).
- **Syntax highlighting** – Highlight YAML and JSON in textareas and result area.
- **Dark mode** – Toggle or system preference for dark theme.
- **Sample / templates** – Dropdown or buttons to load example YAML (anchors, lists, etc.).
- **Error location** – Show line/column or snippet when conversion fails.
- **Keyboard shortcut** – e.g. Ctrl+Enter to convert.

---

## DevOps & tooling

- **Python unit tests** – Reintroduce server tests (e.g. index fallback, routing) under `make test` (e.g. pytest or unittest with PyYAML).
- **CI** – GitHub Actions (or similar) to run `make test` and optional Docker build.
- **Version/status endpoint** – e.g. `GET /version` returning app or commit info for deployments.
- **Docker healthcheck** – HEALTHCHECK in Dockerfile using `/health` or curl.
- **Multi-stage build** – Smaller image (e.g. strip dev deps, use slim base).

---

## Performance & reliability

- **Timeouts** – Configurable jq and request timeouts; return 408 or 503 with a clear body.
- **Graceful shutdown** – Drain in-flight requests on SIGTERM before exit.
- **jq process pool** – Reuse a small pool of jq processes instead of spawning per request (if profiling shows spawn cost).
- **Caching** – Cache parsed result for identical POST / body (e.g. short TTL, optional).

---

## Documentation

- **API description** – OpenAPI/Swagger or a small markdown spec for routes, methods, and responses.
- **Anchors/merge** – Short doc or in-app note on supported YAML (anchors, aliases, merge) and current limitations.
- **Contributing** – How to run tests, add a route, add a jqx test.
