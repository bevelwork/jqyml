#!/usr/bin/env python3
"""
Doom-in-jq Python host: runs jq, handles display and input, drives the game loop.
Keyboard only; no mouse. See DOOM_IN_JQ_MILESTONES.md for the plan.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


# Frame schema: { "width": int, "height": int, "draw": [...] } or { "width", "height", "menu": { "lines": [], "selected": n } }; or null (e.g. on quit)
def validate_frame(obj: dict | None) -> bool:
    if obj is None:
        return True
    if not isinstance(obj, dict):
        return False
    if obj.get("width") is None or obj.get("height") is None:
        return False
    if not isinstance(obj["width"], int) or not isinstance(obj["height"], int):
        return False
    draw = obj.get("draw")
    if draw is not None and not isinstance(draw, list):
        return False
    if draw:
        for item in draw:
            if not isinstance(item, dict):
                return False
            if "rect" not in item or "color" not in item:
                return False
            r = item["rect"]
            if not (isinstance(r, list) and len(r) == 4):
                return False
    menu = obj.get("menu")
    if menu is not None:
        if not isinstance(menu, dict):
            return False
        if "lines" not in menu or not isinstance(menu["lines"], list):
            return False
    map_data = obj.get("map")
    if map_data is not None:
        if not isinstance(map_data, dict):
            return False
        if "lines" not in map_data or not isinstance(map_data["lines"], list):
            return False
        for seg in map_data["lines"]:
            if not isinstance(seg, dict) or not all(k in seg for k in ("x1", "y1", "x2", "y2")):
                return False
        if "player" not in map_data or not isinstance(map_data["player"], dict):
            return False
        p = map_data["player"]
        if not all(k in p for k in ("x", "y", "angle")):
            return False
    view3d = obj.get("view3d")
    if view3d is not None:
        if not isinstance(view3d, dict):
            return False
        if "walls" not in view3d or not isinstance(view3d["walls"], list):
            return False
        if "player" not in view3d or not isinstance(view3d["player"], dict):
            return False
    hud = obj.get("hud")
    if hud is not None:
        if not isinstance(hud, dict) or "health" not in hud:
            return False
    return True


def run_jq(script_path: Path, jq_dir: Path, stdin_str: str | None = None, null_input: bool = False) -> str:
    """Run jq with -L jq_dir -f script; optional stdin. null_input=True passes -n (no input). Returns stdout."""
    cmd = ["jq", "-L", str(jq_dir), "-f", str(script_path)]
    if null_input:
        cmd.insert(1, "-n")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=stdin_str,
        cwd=Path(__file__).resolve().parent,
    )
    if result.returncode != 0:
        raise RuntimeError(f"jq failed: {result.stderr or result.stdout}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Doom-in-jq runner")
    parser.add_argument(
        "--once",
        action="store_true",
        default=True,
        help="Run once: emit one static frame from jq and exit (default).",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run one tic of the game loop (state + input -> state + frame).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Do not open a window; only validate frame output (for tests).",
    )
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    jq_dir = base / "jq"

    if args.loop:
        # One tic: pass state + input; include level for E1M1 so menu→game can load it (Phase 3.1)
        level_path = base / "data" / "e1m1.json"
        level_data = None
        if level_path.is_file():
            with open(level_path) as f:
                level_data = json.load(f)
        payload = {
            "state": None,
            "input": {"keys": [], **({"level": level_data} if level_data is not None else {})},
        }
        out = run_jq(jq_dir / "game.jq", jq_dir, stdin_str=json.dumps(payload))
        data = json.loads(out)
        if "state" not in data:
            print("game.jq must output { state, frame }", file=sys.stderr)
            return 1
        if not validate_frame(data.get("frame")):
            print("Invalid frame from game.jq", file=sys.stderr)
            return 1
        if args.headless:
            return 0
        # TODO: render data["frame"]
        return 0

    # --once: static frame from frame.jq (no input)
    out = run_jq(jq_dir / "frame.jq", jq_dir, null_input=True)
    frame = json.loads(out)
    if not validate_frame(frame):
        print("Invalid frame from frame.jq", file=sys.stderr)
        return 1
    if args.headless:
        return 0
    # TODO: open window and draw frame
    print(f"Frame: {frame['width']}x{frame['height']}, {len(frame.get('draw', []))} draw commands", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
