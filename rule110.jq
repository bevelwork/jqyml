# Rule 110 cellular automaton in jq — one-off "proof" that jq is Turing-complete.
# Run: jq -n -r -f rule110.jq
# Optional: --argjson generations 50 (default 50, clamped 1–500), --argjson width 79 (default 79).
# For a ~2s flash: jq -n -r -f rule110.jq | while IFS= read -r line; do printf '\r%s' "$line"; sleep 0.04; done

def rule110_triple:
  {
    "111": 0, "110": 1, "101": 1, "100": 0,
    "011": 1, "010": 1, "001": 1, "000": 0
  }[map(tostring) | join("")];

def next_row:
  [range(0; length) as $i
   | [ (if $i > 0 then .[$i - 1] else 0 end),
       .[$i],
       (if $i + 1 < length then .[$i + 1] else 0 end) ]
   | rule110_triple];

def row_to_str:
  map(if . == 1 then "█" else " " end) | add;

# Single 1 in center; width from $width (default 79)
def initial_row($w):
  ($w / 2 | floor) as $c | [range(0; $w) | if . == $c then 1 else 0 end];

# limit + recurse gives exactly n generations from initial row
(($width // 79) | if . < 1 then 79 else . end) as $w
| (($generations // 50) | if . > 500 then 500 elif . < 1 then 1 else . end) as $n
| initial_row($w)
| [limit($n; recurse(next_row))]
| .[]
| row_to_str
