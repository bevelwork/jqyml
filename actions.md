# jq / functional programming code review — actions

Review focus: jq idioms, functional style, maintainability, and correctness. Items are ordered by file/area.

---

## jqx.jq

### 1. Replace magic iteration caps with “until stable” or named constants
- **Where:** `expand_if` and `expand_for` use `reduce range(0; 100)`; `expand_includes` uses `reduce range(0; 20)`.
- **Why:** 100/20 are arbitrary; deeply nested or many includes could hit the cap and silently stop expanding, or you waste iterations on short templates.
- **Action:** Prefer “until no change” (e.g. `recurse` + `select`, or a helper that stops when `expand_one_*` returns the same string) so expansion is bounded by the template, not a constant. If you keep a cap, define e.g. `def MAX_IF_DEPTH: 100;` and use it so the limit is documented and tunable.

### 2. Document or fix substitution order in `substitute_vars`
- **Where:** `substitute_vars($vars)` uses `[scan("...")] | unique[]` then `reduce ... as $ph (.; gsub($ph; ...))`.
- **Why:** `unique` sorts; substitution order is therefore by string order of placeholders. If you ever have overlapping placeholders (e.g. `{foo}` and `{foobar}`) or placeholders whose value contains another placeholder, order can matter. Currently you only substitute `{identifier}` style, so overlap is unlikely, but it’s implicit.
- **Action:** Either (a) document that substitution order is unspecified (and that overlapping placeholders are not supported), or (b) substitute in left-to-right occurrence order: e.g. repeatedly find the first `{...}` with `index`/`capture`, substitute it, and recurse on the rest until none remain.

### 3. Factor repeated “propagate stack to parent” logic in component tag search
- **Where:** `_first_component_tag` repeats similar logic for several patterns (`"  <" + name + " />"`, `"\n  <" + ...`, `"\n    <" + ...`, `"<" + name + " />"`, `"<" + name + "/>"`), each with slightly different `pos`/`len`.
- **Action:** Consider a small helper, e.g. `def _tag_match($t; $name; $prefix; $suffix): ($t | index($prefix + $name + $suffix)) as $p | if $p != null then {pos: $p, len: ($prefix | length) + ($name | length) + ($suffix | length)} else null end`, then build the list of candidates from a table of [prefix, suffix] and take `min_by(.pos)` among non-null. Reduces duplication and makes adding variants (e.g. different spacing) easier.

### 4. Consider escaping placeholder text for `gsub` in `substitute_vars`
- **Where:** `gsub($ph; ($vars[$ph[1:-1]] // "" | tostring))` — `$ph` is a literal string like `"{count}"`.
- **Why:** In jq, `gsub(re; repl)` treats `re` as a regex. `{` and `}` can be significant in some regex contexts. For maximum safety and clarity, use a literal (non-regex) replacement: e.g. split the string on the literal placeholder and join with the value, or use a regex built from escaped literal (if jq supports it).
- **Action:** If you want to be robust to future placeholder shapes, replace using string split/join on the literal `$ph` instead of `gsub`, e.g. `split($ph) | join($value)` (and escape `$value` if it could contain `$ph`). Otherwise, document that placeholders must be `{identifier}` and that values must not contain `{`/`}` if they could be mistaken.

### 5. Final fallback branch in main pipeline
- **Where:** Line 159: `(if $s4 != null and ($s4 | length) > 0 then $s4 elif $s1 != null ... else "" end)`.
- **Why:** Falling back to `$s1` (after includes, before if/for/vars) when `$s4` is empty can be surprising (e.g. a template that expands to empty would still show included-but-unexpanded content).
- **Action:** Document this fallback in the header comment, or simplify to “output `$s4` or `""`” so behavior is predictable.

---

## parse.jq

### 6. Remove dead branch for path
- **Where:** `$path == "/rule110" or ($path | startswith("/rule110?"))`.
- **Why:** `$path` is set from `(.path | split("?")[0])`, so it never contains `?`. The `startswith("/rule110?")` branch is never true.
- **Action:** Use only `$path == "/rule110"`.

### 7. Consider data-driven routing
- **Where:** Long `if $method == "GET" and $path == "/" then ... elif ... else ... end` chain.
- **Action:** Optionally refactor to a list of `{method, path_match, action, body_key?}` and use `first(.[] | select(...))` (e.g. path_match as a test or regex). Keeps routing in one structure and makes adding routes (e.g. favicon, robots) easier without touching parse.jq if you later drive more from jq.

---

## state.jq

### 8. Preserve all keys from `current_state` explicitly
- **Where:** `new_state: (.current_state | .counter += 1 | .transforms = (.transforms // 0))`.
- **Why:** Currently other keys are preserved because you’re mutating the same object. If someone later changes the pipeline (e.g. builds a new object with only `counter` and `transforms`), keys like custom metrics could be dropped.
- **Action:** Either document “new_state is current_state with counter and transforms updated; other keys preserved,” or construct new_state explicitly as `current_state + {counter: ..., transforms: ...}` so preservation is obvious and robust to refactors.

---

## yaml.jq

### 9. Unify or document `split_colon` vs `split_colon2`
- **Where:** `split_colon(s)` splits on every colon; `split_colon2(s)` splits on first colon only. Only `key_line_handler` uses `split_colon`; `key_value_line_handler` uses `split_colon2`.
- **Action:** Either remove `split_colon` and inline “split on first colon” only where needed, or add a one-line comment that `split_colon` is “all colons” (for key-only lines) and `split_colon2` is “first colon only” (for key: value). Prevents future misuse.

### 10. Extract “propagate stack to parent” into a def
- **Where:** In `_process_line`, the pattern `(if (.stack | length) > 1 and .stack[0].key != null then reduce range(0; .stack | length - 1) as $i (.; .stack[$i + 1].obj[.stack[$i].key] = .stack[$i].obj) else . end)` appears three times.
- **Action:** Define e.g. `def _propagate_stack: if (.stack | length) > 1 and .stack[0].key != null then reduce range(0; .stack | length - 1) as $i (.; .stack[$i + 1].obj[.stack[$i].key] = .stack[$i].obj) else . end`, and call it in all three branches. Reduces duplication and keeps stack semantics in one place.

### 11. Break up `_process_line` into smaller defs
- **Where:** `_process_line` is one large function handling block scalars, key, key_value (with anchor/alias/merge), and list_item.
- **Action:** Split into e.g. `_process_block_scalar_line`, `_process_key_value_line` (with anchor/alias/merge/coerce_value), `_process_list_item_line`, and have `_process_line` dispatch by `$line.type` and block_scalar state. Improves readability and testability (you could test key_value handling in isolation).

### 12. Recursion depth in `find_matching_endif` (jqx) vs YAML
- **Where:** (jqx) `find_matching_endif` is recursive; (yaml) `_pop_until_indent` is recursive.
- **Why:** Very deeply nested templates or YAML could hit jq’s recursion limit. Unlikely in normal use.
- **Action:** Low priority. If you ever see “recursion depth exceeded,” consider rewriting to an iterative loop (e.g. `reduce` over positions) instead of recursion.

---

## rule110.jq

### 13. Make width and default generations configurable
- **Where:** Width `79` and default `$generations // 50` are literals.
- **Action:** Use `$width // 79` and keep `$generations` as is (already `--argjson`). Document in the header: “Optional: --argjson width 79, --argjson generations 50.”

### 14. Style: `recurse` + `limit` is idiomatic
- **Where:** `[limit($n; recurse(next_row))] | .[] | row_to_str`.
- **Why:** This is good jq: no manual loop, clear “n rows starting from initial.”
- **Action:** No change; consider a short comment that “limit + recurse” gives exactly n generations.

---

## index.jq / built_with.jq

### 15. Reduce duplication between static HTML generators
- **Where:** Both files use the same pattern `[ "line1", "line2", ... ] | join("\n")` with overlapping CSS and structure.
- **Action:** Consider a small shared fragment (e.g. a jq module that emits common style lines or head/body skeleton) or a single “static page” def that takes title and body lines. Low priority if these are fallbacks only.

---

## General / repo

### 16. Ensure `empty.jqx` exists and is tracked
- **Where:** `server.py` and Dockerfile reference `empty.jqx`; glob search shows no such file in the repo.
- **Action:** Add an `empty.jqx` file (empty or single newline) and commit it, or have the Makefile/build create it so `jq` never gets a missing file.

### 17. Log level and performance
- **Where:** `run.jq` and `parse_yaml` use `slog("debug"; ...)` / `slog("info"; ...)` on every convert and parse.
- **Action:** If you add a “verbose” or “debug” mode, gate debug logs so production doesn’t pay for string building and stderr. Info-level “convert_start”/“convert_ok” are fine for request-level observability.

### 18. Consistent use of `include "log"`
- **Where:** `parse.jq`, `run.jq`, `state.jq`, `yaml.jq` include log; `jqx.jq` does not.
- **Action:** Optional: add `include "log"` to `jqx.jq` only if you want template-level debug (e.g. “expand_includes iteration N”). Otherwise leave as-is and document that jqx is silent.

---

## Summary table

| #  | Area              | Priority | Effort |
|----|-------------------|----------|--------|
| 1  | jqx iteration cap | Medium   | Low    |
| 2  | substitute_vars order | Low  | Low    |
| 3  | _first_component_tag factor | Low | Medium |
| 4  | gsub literal      | Low      | Low    |
| 5  | jqx fallback doc  | Low      | Low    |
| 6  | parse.jq dead branch | Low   | Trivial |
| 7  | parse.jq data-driven | Low   | Medium |
| 8  | state new_state   | Low      | Low    |
| 9  | split_colon doc   | Low      | Trivial |
| 10 | yaml stack propagate def | Medium | Low |
| 11 | yaml _process_line split | Medium | Medium |
| 12 | recursion depth   | Low      | Medium |
| 13 | rule110 width     | Low      | Trivial |
| 14 | rule110 comment   | Low      | Trivial |
| 15 | index/built_with share | Low | Medium |
| 16 | empty.jqx         | High     | Trivial |
| 17 | log level         | Low      | Low    |
| 18 | jqx include log   | Low      | Trivial |
