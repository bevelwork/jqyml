# doom_jq tests

Tests are driven by the root `Makefile`. Run from repo root:

```bash
make test-doom-jq          # all doom_jq tests
make test-doom-jq-frame    # Phase 1.0: static frame
make test-doom-jq-loop    # Phase 1.1: one tic (loop.jq)
make test-doom-jq-game    # Phase 2: menu flow (game.jq)
make test-doom-jq-runner  # runner.py --headless and --loop --headless
```

`make test` (full suite) includes `test-doom-jq`.

## What each target does

| Target | Asserts |
|--------|--------|
| **test-doom-jq-frame** | `jq -n -f doom_jq/jq/frame.jq` outputs JSON that matches `doom_jq/tests/frame_static.expected` (exact snapshot). |
| **test-doom-jq-loop** | `echo '{"state":null,"input":{"keys":[]}}' \| jq -f doom_jq/jq/loop.jq` matches `loop_one_tic.expected` (one bouncing-box tic). |
| **test-doom-jq-game** | Three snapshots: (1) null state → main menu; (2) main + Enter → episode screen; (3) episode + Enter (E1) → skill screen. Each run is `jq -f doom_jq/jq/game.jq` with the given state/input; output is diff’d against the corresponding `.expected` file. |
| **test-doom-jq-runner** | `python3 doom_jq/runner.py --headless` and `python3 doom_jq/runner.py --loop --headless` both exit 0. Runner runs jq (frame.jq once, game.jq one tic) and validates frame schema (draw or menu or null). |

## Validation (as of 2026-02-24)

- All four targets pass when implementation and expected files match.
- **Regression:** If an expected file is corrupted (e.g. wrong content), the corresponding target fails with exit 1, prints “FAILED” and the diff.
- **Full suite:** `make test` runs jqx, state, anchors, speed, server, and doom_jq; all pass.
- **Runner:** `validate_frame()` accepts frames with `draw`, with `menu` (lines + selected), or null; rejects frames missing required fields (e.g. no `width`).
