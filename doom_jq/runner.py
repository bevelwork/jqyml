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


# Frame schema: { "width": int, "height": int, "draw": [ {"rect": [x,y,w,h], "color": "#rrggbb"}, ... ] }
def validate_frame(obj: dict) -> bool:
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
        # One tic: pass {"state": null, "input": {"keys": []}} to loop.jq
        payload = {"state": None, "input": {"keys": []}}
        out = run_jq(jq_dir / "loop.jq", jq_dir, stdin_str=json.dumps(payload))
        data = json.loads(out)
        if "state" not in data or "frame" not in data:
            print("loop.jq must output { state, frame }", file=sys.stderr)
            return 1
        if not validate_frame(data["frame"]):
            print("Invalid frame from loop.jq", file=sys.stderr)
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
