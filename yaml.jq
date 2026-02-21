# YAML parsing shim for jq (indentation-based, no external deps).
# Usage: parse_yaml($raw_string) or parse_yaml($input)

#c Safe split: input must be a string (avoids "split must be strings" error)
def safe_split_newlines:
  if type != "string" then [] else split("\n") end;

# Split string into lines
def lines:
  safe_split_newlines;

# Strip leading/trailing whitespace (coerce to string for gsub)
def strip:
  (tostring | gsub("^[ \t]+"; "") | gsub("[ \t]+$"; ""));

# Number of leading spaces (indent depth)
def get_indent:
  (tostring | capture("^(?<spaces>[ ]*)") | .spaces | length);

# Strip inline comment (space + # to end of line) so "is # comment" -> "is"
def strip_inline_comment:
  (tostring | gsub("\\s+#.*$"; "") | gsub("[ \t]+$"; ""));

# Safe split: only split strings. split/1 only; no second arg (jq split separator must be string)
def split_colon(s): (s | if type != "string" then [] else split(":") end);
# Split on first colon only: [key, value_with_rest]
def split_colon2(s):
  (s | if type != "string" then [s, null] else split(":") end)
  | if length >= 2 then [.[0], (.[1:] | join(":"))] else [.[0], null] end;

# Parse a single line: returns { type, key, value, indent } or null
# Use stripped content for type/key/value so indented lines (e.g. "  should: true") match
def parse_line:
  if type != "string" then error("parse_line expects string, got \(type)") else . end
  | . as $line
  | ($line | strip) as $stripped
  | ($line | get_indent) as $indent
  | $stripped
  | select(length > 0)
  | if $stripped | startswith("- ") then
      { type: "list_item", value: ($stripped | .[2:] | strip | strip_inline_comment), indent: $indent }
    elif $stripped | test("^[a-zA-Z0-9_-]+:\\s*$") then
      { type: "key", key: (split_colon($stripped)[0] | strip), value: null, indent: $indent }
    elif $stripped | test("^[a-zA-Z0-9_-]+:\\s*.+") then
      (split_colon2($stripped) | .[0] |= strip | .[1] |= (if . != null then (strip | strip_inline_comment) else . end)) as $parts
      | { type: "key_value", key: $parts[0], value: $parts[1], indent: $indent }
    else
      { type: "scalar", value: ($stripped | strip_inline_comment), indent: $indent }
    end;

# Build a list of parsed line objects (skip empty/comments)
def parsed_lines:
  lines
  | map(select(length > 0 and (startswith("#") | not)))
  | map(parse_line);

# Reduce parsed lines into a single JSON value (object or array)
def parse_yaml:
  (if type == "string" then . else "" end) as $raw
  | $raw | parsed_lines as $lines
  | reduce $lines[] as $line (
      { stack: [{}], last_key: null };
      . as $state
      | if $line.type == "key" then
          $state
          | .stack[0][$line.key] = null
          | .last_key = $line.key
        elif $line.type == "key_value" then
          $state
          | .stack[0][$line.key] = $line.value
          | .last_key = $line.key
        elif $line.type == "list_item" then
          $state
          | (.stack[0][$state.last_key] |= (if . == null then [$line.value] else . + [$line.value] end))
        else
          $state
        end
    )
  | .stack[0];

# Convenience: parse YAML string and emit JSON
def parse_yaml_string:
  parse_yaml;
