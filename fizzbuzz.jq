# FizzBuzz in jq: for 1..n output number, Fizz, Buzz, or FizzBuzz.
# Run: jq -n -r -f fizzbuzz.jq
# Optional: --argjson n 30 (default 30, clamped 1–500).

(($n // 30) | if . > 500 then 500 elif . < 1 then 1 else . end) as $limit
| range(1; $limit + 1)
| if . % 15 == 0 then "FizzBuzz"
  elif . % 5 == 0 then "Buzz"
  elif . % 3 == 0 then "Fizz"
  else tostring
  end
