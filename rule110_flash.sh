#!/usr/bin/env bash
# ~2-second flash of Rule 110 cellular automata (pure jq). Prove it.
# Usage: ./rule110_flash.sh   or: bash rule110_flash.sh

set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAMES=50
DELAY="0.04"   # 50 * 0.04 = 2s

printf '\033[2J\033[H'   # clear and home
jq -n -r -L "$DIR" -f "$DIR/rule110.jq" | while IFS= read -r line; do
  printf '\r\033[K%s\n' "$line"
  sleep "$DELAY"
done
printf '\r\033[KRule 110 in jq — Turing complete.\n'
