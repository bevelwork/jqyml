#!/usr/bin/env python3
"""Run run.jq on a YAML file N times and report total and per-iteration time."""
import os
import subprocess
import time

def main():
    n = int(os.environ.get("ITERATIONS", "50"))
    f = os.environ.get("SPEED_YAML", "tests/03_simple_key_value.yaml")
    if not os.path.isfile(f):
        print(f"Missing {f}")
        raise SystemExit(1)
    print(f"Speed test: run.jq on {f} x {n} iterations")
    with open(f) as fp:
        data = fp.read()
    start = time.perf_counter()
    for _ in range(n):
        subprocess.run(
            ["jq", "-R", "-s", "-L", ".", "-rf", "run.jq"],
            input=data.encode("utf-8"),
            capture_output=True,
            timeout=30,
            cwd=os.getcwd(),
        )
    elapsed = time.perf_counter() - start
    print(f"  Total:   {elapsed:.3f} s")
    print(f"  Per run: {elapsed / n * 1000:.2f} ms ({n} iterations)")

if __name__ == "__main__":
    main()
