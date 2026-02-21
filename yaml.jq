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

# Unquote YAML-style quoted strings: "supported" -> supported, 'x''y' -> x'y
def unquote_yaml_string:
  if type != "string" then . else
    . as $s
    | if ($s | length) >= 2 and ($s | startswith("\"")) and ($s | endswith("\"")) then
        $s[1:-1] | gsub("\\\\"; "\\") | gsub("\\\""; "\"")
      elif ($s | length) >= 2 and ($s | startswith("'")) and ($s | endswith("'")) then
        $s[1:-1] | gsub("''"; "'")
      else $s end
  end;

# YAML 1.2: only true and false (case-sensitive) are booleans; Yes/No/On/Off etc. are strings
def _parse_bool:
  if type != "string" then null else
    if . == "true" then true
    elif . == "false" then false
    else null end
  end;

# Coerce key_value: quoted -> string; unquoted -> number, then bool, else string
def coerce_value:
  if type != "string" then . else
    . as $s
    | if ($s | length) >= 2 and (($s | startswith("\"")) and ($s | endswith("\"")) or ($s | startswith("'")) and ($s | endswith("'"))) then
        $s | unquote_yaml_string
      else
        ($s | try tonumber catch null) as $n
        | if $n != null then $n
          else ($s | _parse_bool) as $b
          | if $b != null then $b else $s end
          end
      end
  end;

# Parse flow-style embedded lists: "[[][][]]" -> [[],[],[]] by inserting commas then fromjson
def _parse_embedded_lists:
  if type != "string" then . else
    (gsub("\\]\\s*\\["; "], [") | try fromjson catch null) as $parsed
    | if $parsed != null then $parsed else . end
  end;

# List item value: "[]" -> []; "[[]...]" -> parsed nested arrays; else leave as-is
def coerce_list_item_value:
  if type != "string" then . else
    if . == "[]" then []
    elif (startswith("[") and endswith("]") and (test("^[\\[\\]\\s]+$"))) then _parse_embedded_lists
    else . end
  end;

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
      { type: "list_item", value: ($stripped | .[2:] | strip | strip_inline_comment | unquote_yaml_string), indent: $indent }
    elif $stripped | test("^[a-zA-Z0-9_-]+:\\s*$") then
      { type: "key", key: (split_colon($stripped)[0] | strip), value: null, indent: $indent }
    elif $stripped | test("^[a-zA-Z0-9_-]+:\\s*.+") then
      (split_colon2($stripped) | .[0] |= strip | .[1] |= (if . != null then (strip | strip_inline_comment) else . end)) as $parts
      | { type: "key_value", key: $parts[0], value: $parts[1], indent: $indent }
    else
      { type: "scalar", value: ($stripped | strip_inline_comment | unquote_yaml_string), indent: $indent }
    end;

# Build a list of parsed line objects (skip empty/comments)
def parsed_lines:
  lines
  | map(select(length > 0 and (startswith("#") | not)))
  | map(parse_line);

# Reduce parsed lines into a single JSON value (object or array).
# Stack entries: {obj: object, indent: number, key: string}. stack[0] is current (deepest).
# Pop stack until top.indent < line.indent so indented lines nest under the right parent.
# Propagate current.obj back to parent.obj[current.key] after updates (jq is immutable).
def _pop_until_indent($line_indent):
  if length <= 1 then .
  elif .[0].indent >= $line_indent then .[1:] | _pop_until_indent($line_indent)
  else . end;

def parse_yaml:
  (if type == "string" then . else "" end) as $raw
  | $raw | parsed_lines as $lines
  | reduce $lines[] as $line (
      { stack: [{obj: {}, indent: -1, key: null}], last_key: null };
      . as $state
      | .stack = ($state.stack | _pop_until_indent($line.indent))
      | . as $state2
      | if $line.type == "key" then
          $state2
          | .stack[0].obj[$line.key] = {}
          | .stack = ([{obj: .stack[0].obj[$line.key], indent: $line.indent, key: $line.key}] + .stack)
          | .last_key = $line.key
        elif $line.type == "key_value" then
          $state2
          | .stack[0].obj[$line.key] = ($line.value | coerce_value)
          | .last_key = $line.key
          # Propagate full stack so root sees nested updates (jq is immutable)
          | (if (.stack | length) > 1 then reduce range(0; .stack | length - 1) as $i (.; .stack[$i + 1].obj[.stack[$i].key] = .stack[$i].obj) else . end)
        elif $line.type == "list_item" then
          # List items belong to the parent's last_key (the key that introduced the list block)
          ($line.value | coerce_list_item_value) as $item_val
          | $state2
          | (if (.stack | length) > 1 then .stack[1].obj[$state2.last_key] else .stack[0].obj[$state2.last_key] end) as $cur
          | (if (.stack | length) > 1 then
              .stack[1].obj[$state2.last_key] = (if $cur == null or ($cur | type) == "object" and ($cur | keys | length) == 0 then [$item_val] else $cur + [$item_val] end)
            else
              .stack[0].obj[$state2.last_key] = (if $cur == null or ($cur | type) == "object" and ($cur | keys | length) == 0 then [$item_val] else $cur + [$item_val] end)
            end)
          | (if (.stack | length) > 1 then .stack = .stack[1:] else . end)
          | .last_key = $state2.last_key
        else
          $state2
        end
    )
  | .stack[.stack | length - 1].obj;

# Convenience: parse YAML string and emit JSON
def parse_yaml_string:
  parse_yaml;
