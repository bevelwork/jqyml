# Rule 110 cellular automaton in jq — one-off "proof" that jq is Turing-complete.
# Run: jq -n -r -f rule110.jq
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

# Width 79, single 1 in center
def initial_row:
  (79 / 2 | floor) as $c | [range(0; 79) | if . == $c then 1 else 0 end];

# $generations from --argjson (default 50, cap 1–500)
(($generations // 50) | if . > 500 then 500 elif . < 1 then 1 else . end) as $n
| initial_row
| [limit($n; recurse(next_row))]
| .[]
| row_to_str
