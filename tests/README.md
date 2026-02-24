# tests/

## jqx composition tests (`tests/jqx/`)

The jqx test harness (`make test-jqx`) runs every `tests/jqx/*.jqx` file (except component-only files) as a test case:

- **Main template**: `tests/jqx/<name>.jqx` — the template under test.
- **Input**: `tests/jqx/<name>.json` — JSON input (vars) for the template.
- **Expected output**: `tests/jqx/<name>.expected` — exact string to compare against.

### Composing templates (Header / Head / Footer)

A test can compose a main template with optional **component** templates. If present, they are passed to jq and expanded where the main template uses `<Header />`, `<Head />`, or `<Footer />`:

| Slot       | Optional file                    | Tag in main template |
|-----------|-----------------------------------|----------------------|
| Header    | `tests/jqx/<name>.header.jqx`    | `<Header />`         |
| Head      | `tests/jqx/<name>.head.jqx`      | `<Head />`           |
| Footer    | `tests/jqx/<name>.footer.jqx`    | `<Footer />`         |

- If a component file is **missing**, that slot is empty (no expansion).
- Component templates are processed with the **same** input vars as the main template (so they can use `{var}`, `<If>`, `<For>`).
- Test names are derived from the main `.jqx` file only; `*.header.jqx`, `*.head.jqx`, and `*.footer.jqx` are excluded from the test list so they are not run as standalone tests.

### Example composition tests

- **15_include_header** — main template uses `<Header />`; `.header.jqx` provides the fragment. Validates single-slot composition.
- **16_compose_header_footer** — main template uses `<Header />` and `<Footer />`. Validates two slots and order.
- **17_compose_head** — main template uses `<Head />` and vars in both main and head. Validates Head slot and shared vars.
- **18_compose_all_slots** — main template uses `<Head />`, `<Header />`, and `<Footer />`. Validates full composition.
- **19_compose_component_gets_vars** — Header component uses `{title}`, `{count}`, and `<If show_count>`. Validates that composed components receive the same vars and support conditionals.

These tests guard against regressions in component expansion, variable passing, and slot order.
