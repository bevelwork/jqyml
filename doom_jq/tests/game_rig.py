#!/usr/bin/env python3
"""
Doom-in-jq game test rig: run a sequence of inputs through game.jq and assert expected state.

Usage:
  python3 doom_jq/tests/game_rig.py doom_jq/tests/cases/backward_from_center.json
  python3 doom_jq/tests/game_rig.py doom_jq/tests/cases/*.json   # run all cases in dir

Test case JSON format:
  {
    "name": "optional test name",
    "initial": { ... }  or  "initial": "game_center"  (preset: game, level, player 128,128 @ 90°),
    "steps": [
      { "keys": ["Down"], "expect": { "player": { "x": 128, "y": 120 } } },
      { "keys": ["Up", "Up"], "expect": { "player": { "y": "~136" } } }  // "~N" = within 1 of N
    ]
  }

Expect values can be:
  - number: exact match (after rounding for display)
  - string "~N": state value within 1 of N (tolerance for float)
  - object with "min", "max": value in range inclusive
"""

import json
import subprocess
import sys
from pathlib import Path

# Rig runs from repo root or from doom_jq; find paths accordingly
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOOM_JQ_DIR = Path(__file__).resolve().parent.parent
JQ_DIR = DOOM_JQ_DIR / "jq"
GAME_JQ = JQ_DIR / "game.jq"
LEVEL_PATH = DOOM_JQ_DIR / "data" / "e1m1.json"

TOLERANCE = 5.0  # for "~N" asserts (covers float drift from sin/cos)


def load_level() -> dict | None:
    if not LEVEL_PATH.is_file():
        return None
    with open(LEVEL_PATH, encoding="utf-8") as f:
        return json.load(f)


def preset_initial(name: str, level_data: dict) -> dict:
    if name == "game_center":
        return {
            "mode": "game",
            "level": level_data,
            "player": {"x": 128, "y": 128, "angle": 90, "health": 100},
        }
    if name == "game_north_wall":
        # At north boundary (y=256), facing south (270°). Backward = north = (128, 264) = blocked.
        return {
            "mode": "game",
            "level": level_data,
            "player": {"x": 128, "y": 256, "angle": 270, "health": 100},
        }
    if name == "game_south_wall":
        # At south boundary (y=0), facing north (90°). Backward = south = (128, -8) = blocked.
        return {
            "mode": "game",
            "level": level_data,
            "player": {"x": 128, "y": 0, "angle": 90, "health": 100},
        }
    if name == "game_east_wall":
        # At east boundary (x=256), facing west (180°). Backward = east = (264, 128) = blocked.
        return {
            "mode": "game",
            "level": level_data,
            "player": {"x": 256, "y": 128, "angle": 180, "health": 100},
        }
    if name == "game_west_wall":
        # At west boundary (x=0), facing east (0°). Backward = west = (-8, 128) = blocked.
        return {
            "mode": "game",
            "level": level_data,
            "player": {"x": 0, "y": 128, "angle": 0, "health": 100},
        }
    raise ValueError(f"unknown preset: {name}")


def run_tic(state: dict, keys: list[str], level_data: dict | None) -> dict:
    payload = {
        "state": state,
        "input": {"keys": keys, **({"level": level_data} if level_data else {})},
    }
    cmd = ["jq", "-L", str(JQ_DIR), "-f", str(GAME_JQ), "-c"]
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=5,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"jq failed: {proc.stderr or proc.stdout}")
    out = json.loads(proc.stdout)
    if "state" not in out:
        raise RuntimeError("game.jq must output { state, frame }")
    return out["state"]


def _match_expect(got: float | int, expect) -> tuple[bool, str]:
    if isinstance(expect, (int, float)):
        if abs(got - expect) < 0.001:
            return True, ""
        return False, f"got {got} expected {expect}"
    if isinstance(expect, str) and expect.startswith("~"):
        try:
            target = float(expect[1:])
        except ValueError:
            return False, f"invalid ~ value: {expect}"
        if abs(got - target) <= TOLERANCE:
            return True, ""
        return False, f"got {got} expected ~{target} (tol {TOLERANCE})"
    if isinstance(expect, dict):
        if "min" in expect and got < expect["min"]:
            return False, f"got {got} expected >={expect['min']}"
        if "max" in expect and got > expect["max"]:
            return False, f"got {got} expected <={expect['max']}"
        return True, ""
    return False, f"unhandled expect type: {type(expect)}"


def assert_state(actual: dict, expect: dict, step_index: int) -> list[str]:
    errors = []
    for key, exp_val in expect.items():
        if key == "player" and isinstance(exp_val, dict):
            p = actual.get("player") or {}
            for pk, pv in exp_val.items():
                got = p.get(pk)
                if got is None:
                    errors.append(f"step {step_index}: player.{pk} missing")
                    continue
                ok, msg = _match_expect(got, pv)
                if not ok:
                    errors.append(f"step {step_index}: player.{pk} {msg}")
        else:
            got = actual.get(key)
            if got is None:
                errors.append(f"step {step_index}: {key} missing")
            else:
                ok, msg = _match_expect(got, exp_val)
                if not ok:
                    errors.append(f"step {step_index}: {key} {msg}")
    return errors


def run_case(case_path: Path, level_data: dict | None) -> list[str]:
    with open(case_path, encoding="utf-8") as f:
        case = json.load(f)
    name = case.get("name", case_path.name)
    initial = case.get("initial")
    if isinstance(initial, str):
        if not level_data:
            return [f"{name}: no level data for preset '{initial}'"]
        state = preset_initial(initial, level_data)
    else:
        state = dict(initial) if initial else {}
        if state.get("level") is None and level_data:
            state["level"] = level_data

    steps = case.get("steps", [])
    errors = []
    step_index = 0
    for step in steps:
        keys = step.get("keys", [])
        repeat = step.get("repeat", 1)
        expect = step.get("expect")
        for r in range(repeat):
            state = run_tic(state, keys, level_data)
            if expect is not None and r == repeat - 1:
                errors.extend(assert_state(state, expect, step_index))
            step_index += 1
    return errors


def main() -> int:
    level_data = load_level()
    if not level_data:
        print("game_rig: warning: no doom_jq/data/e1m1.json, tests using level will fail", file=sys.stderr)

    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print("Usage: game_rig.py <case.json> [case2.json ...]", file=sys.stderr)
        return 1

    failed = 0
    for path in paths:
        if not path.is_file():
            print(f"Skip (not file): {path}", file=sys.stderr)
            continue
        errs = run_case(path, level_data)
        if errs:
            failed += 1
            print(f"FAIL {path}")
            for e in errs:
                print(f"  {e}")
        else:
            print(f"OK   {path}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
