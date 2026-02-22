# YAML parsing shim for jq (indentation-based, no external deps).
# Usage: parse_yaml($raw_string) or parse_yaml($input)
include "log";

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

# ---------------------------------------------------------------------------
# Detection: classify what type a value is (returns a type label).
# ---------------------------------------------------------------------------

# Key/value scalar: quoted string, number, bool, embedded JSON ([...] or {...}), or string
def detect_key_value_type:
  if type != "string" then "string" else
    if (length >= 2) and ((startswith("\"") and endswith("\"")) or (startswith("'") and endswith("'"))) then "quoted_string"
    elif (try tonumber catch null) != null then "number"
    elif (if . == "true" then true elif . == "false" then false else null end) != null then "bool"
    elif (length >= 2) and ((startswith("[") and endswith("]")) or (startswith("{") and endswith("}"))) then "embedded_json"
    else "string"
    end
  end;

# List item value: empty list "[]", embedded list "[[]...]", or string
def detect_list_item_type:
  if type != "string" then "string" else
    if . == "[]" then "empty_list"
    elif (startswith("[") and endswith("]") and test("^[\\[\\]\\s]+$")) then "embedded_list"
    else "string"
    end
  end;

# ---------------------------------------------------------------------------
# Handlers: given raw string (and type), return the coerced value.
# ---------------------------------------------------------------------------

def string_handler:  unquote_yaml_string;
def number_handler:  tonumber;
def bool_handler:   if . == "true" then true else false end;
def default_string_handler: .;

# Try to parse string as JSON; return parsed value or original string
def try_parse_json:
  if type != "string" then . else
    . as $s
    | if ($s | length >= 2) and (($s | startswith("[")) or ($s | startswith("{"))) then
        (try ($s | fromjson) catch null) as $parsed
        | if $parsed != null then $parsed else $s end
      else $s
    end
  end;

def empty_list_handler:   [];
def embedded_list_handler:
  (gsub("\\]\\s*\\["; "], [") | try fromjson catch null) as $parsed
  | if $parsed != null then $parsed else . end;

# ---------------------------------------------------------------------------
# Coerce: detect type, then dispatch to the right handler.
# ---------------------------------------------------------------------------

def coerce_value:
  if type != "string" then . else
    . as $raw
    | ($raw | detect_key_value_type) as $t
    | (if   $t == "quoted_string" then $raw | string_handler
       elif $t == "number"        then $raw | number_handler
       elif $t == "bool"         then $raw | bool_handler
       elif $t == "embedded_json" then (try ($raw | fromjson) catch null) as $parsed | if $parsed != null then $parsed else $raw end
       else                       $raw | default_string_handler
       end) as $result
    # Quoted strings stay string; only try JSON parse for unquoted string values
    | if $t == "quoted_string" then $result
      elif ($result | type) == "string" then $result | try_parse_json
      else $result end
  end;

def coerce_list_item_value:
  if type != "string" then . else
    . as $raw
    | ($raw | detect_list_item_type) as $t
    | if   $t == "empty_list"   then empty_list_handler
      elif $t == "embedded_list" then $raw | embedded_list_handler
      else                         $raw | default_string_handler
      end
  end;

# Safe split: only split strings. split/1 only; no second arg (jq split separator must be string)
def split_colon(s): (s | if type != "string" then [] else split(":") end);
# Split on first colon only: [key, value_with_rest]
def split_colon2(s):
  (s | if type != "string" then [s, null] else split(":") end)
  | if length >= 2 then [.[0], (.[1:] | join(":"))] else [.[0], null] end;

# ---------------------------------------------------------------------------
# Line detection: classify what kind of YAML line this is.
# ---------------------------------------------------------------------------

def detect_line_type:
  if type != "string" then "scalar" else
    . as $stripped
    | if ($stripped | startswith("- ")) or ($stripped | test("^-\\s*$")) then "list_item"
      elif ($stripped | test("^[^:]+:\\s*$")) then "key"
      elif ($stripped | startswith("<<:") or ($stripped | test("^[^:]+:\\s*.+"))) then "key_value"
      else "scalar"
      end
  end;

# ---------------------------------------------------------------------------
# Line handlers: given stripped line + indent, return { type, key?, value?, indent }.
# ---------------------------------------------------------------------------

def list_item_line_handler($indent):
  { type: "list_item", value: ((if startswith("- ") then .[2:] else .[1:] end) | strip | strip_inline_comment | unquote_yaml_string), indent: $indent };

def key_line_handler($indent):
  { type: "key", key: (split_colon(.)[0] | strip), value: null, indent: $indent };

def key_value_line_handler($indent):
  (split_colon2(.) | .[0] |= strip | .[1] |= (if . != null then (strip | strip_inline_comment) else . end)) as $parts
  | { type: "key_value", key: $parts[0], value: $parts[1], indent: $indent };

def scalar_line_handler($indent):
  { type: "scalar", value: (strip_inline_comment | unquote_yaml_string), indent: $indent };

# Reject lines that look like JSON (quoted key or bare { / [) — we expect YAML key: value
def reject_json_like_line:
  if startswith("\"") or startswith("'") then
    error("invalid YAML: line looks like JSON (expected key: value format, not \"key\": value)")
  elif startswith("{") or startswith("[") then
    error("invalid YAML: line looks like JSON (expected key: value format)")
  else . end;

# Parse a single line: detect line type, then call the appropriate handler.
def parse_line:
  if type != "string" then error("parse_line expects string, got \(type)") else . end
  | . as $line
  | ($line | strip) as $stripped
  | ($line | get_indent) as $indent
  | $stripped
  | select(length > 0)
  | reject_json_like_line
  | . as $s
  | ($s | detect_line_type) as $line_t
  | if   $line_t == "list_item"  then $s | list_item_line_handler($indent)
    elif $line_t == "key"        then $s | key_line_handler($indent)
    elif $line_t == "key_value"  then $s | key_value_line_handler($indent)
    else                          $s | scalar_line_handler($indent)
    end;

# Build a list of parsed line objects (include blank lines for block scalars; skip comments). Each has .raw for block scalar content.
def parsed_lines:
  lines
  | map(select(startswith("#") | not))
  | map(if (strip | length) == 0 then {type: "blank", indent: (get_indent), value: "", raw: .} else (. as $raw | parse_line | . + {raw: $raw}) end);

# Block scalar: append one content line. Use .raw so literal content is not altered (e.g. # is not stripped as comment).
def _block_append($line):
  (if $line.type == "blank" then {content: "", indent: $line.indent, blank: true}
   else {content: (if $line.raw then ($line.raw | if $line.indent > 0 then .[$line.indent:] else . end) else (if $line.type == "key_value" then ($line.key + ": " + $line.value) else ($line.value // "") end) end), indent: $line.indent, blank: false}
   end) as $entry
  | .block_scalar.lines += [$entry]
  | (if ($entry.blank | not) and .block_scalar.content_indent == null then .block_scalar.content_indent = $line.indent
     elif ($entry.blank | not) and $line.indent < .block_scalar.content_indent then .block_scalar.content_indent = $line.indent
     else . end);

# Drop trailing blank entries from block scalar lines (YAML clip-chomping: one trailing \n only)
def _trim_trailing_blanks:
  if length > 0 and (.[-1].blank) then .[0:-1] | _trim_trailing_blanks else . end;

# Block scalar: build string from lines (literal | or folded >); append exactly one \n per spec
def _block_build_string:
  .block_scalar as $bs
  | ($bs.lines | _trim_trailing_blanks) as $lines
  | if $bs.type == "literal" then
      ([$lines[] | if .blank then "" else .content end] | join("\n")) + "\n"
    else
      ($bs.content_indent // 0) as $ci
      | (reduce range(0; $lines | length) as $i (""; . as $acc
          | ($lines[$i]) as $ln
          | if $ln.blank then $acc + "\n"
            elif $ln.indent > $ci then $acc + "\n" + $ln.content
            else (if $i > 0 and ($lines[$i - 1].blank | not) then $acc + " " else $acc end) + $ln.content
            end)) + "\n"
    end;

# Block scalar: write key and clear state
def _finalize_block:
  _block_build_string as $str
  | .stack[0].obj[.block_scalar.key] = $str
  | .block_scalar = null;

# Reduce parsed lines into a single JSON value (object or array).
# Stack entries: {obj: object, indent: number, key: string, anchor?: string}. stack[0] is current (deepest).
# Pop stack until top.indent < line.indent; save any popped frame's .anchor into state.anchors.
def _pop_until_indent($line_indent):
  if length <= 1 then .
  elif .[0].indent >= $line_indent then .[1:] | _pop_until_indent($line_indent)
  else . end;

# Pop stack and save anchors from popped frames into state.anchors
def _save_anchors_and_pop($line_indent):
  . as $state
  | $state.stack as $stack
  | ($stack | _pop_until_indent($line_indent)) as $new_stack
  | (($stack | length) - ($new_stack | length)) as $num_popped
  | $state
  | .anchors = ($state.anchors // {}) + (
      reduce range(0; $num_popped) as $i (
        {};
        . + (if $stack[$i].anchor != null then {($stack[$i].anchor): $stack[$i].obj} else {} end)
      )
    )
  | .stack = $new_stack;

# One reduce iteration: state and line -> new state
def _process_line($line):
  . as $state
  | (if $state.block_scalar != null and ($line.indent > $state.block_scalar.key_indent or $line.type == "blank") then
       $state | _block_append($line)
     elif $state.block_scalar != null and $line.indent <= $state.block_scalar.key_indent then
       $state | _finalize_block
     else
       $state
     end) as $state_in
  | if $state.block_scalar != null and ($line.indent > $state.block_scalar.key_indent or $line.type == "blank") then
      $state_in
    else
      $state_in
      | if ($line.type == "list_item" and $line.indent == 0 and (($line.value | strip) == "") and (.stack | length) == 2 and .root_is_list) then
          .stack[1].obj = .stack[1].obj + [.stack[0].obj]
          | .stack[0].obj = {}
        else
          _save_anchors_and_pop($line.indent)
          | . as $state2
          | if ($line.type == "list_item" and $line.indent == 0 and (($line.value | strip) == "") and ($state2.stack | length) == 1) then
              .root_is_list = true
              | .stack = [{obj: {}, indent: 0, key: null}, {obj: [], indent: -1, key: null}]
            elif $line.type == "key" then
              .stack[0].obj[$line.key] = {}
              | .stack = ([{obj: .stack[0].obj[$line.key], indent: $line.indent, key: $line.key}] + .stack)
              | .last_key = $line.key
            elif $line.type == "key_value" then
              (($line.value | strip) | test("^[|>]")) as $is_block_scalar
              | (($line.value | strip) | if test("^\\|") then "literal" else "folded" end) as $block_type
              | if $is_block_scalar then
                   .block_scalar = {key: $line.key, type: $block_type, key_indent: $line.indent, content_indent: null, lines: []}
                 else
                   ($line.value | strip) as $val
                   | (if ($val | test("^&[a-zA-Z0-9_-]+$")) then ($val | capture("^&(?<name>[a-zA-Z0-9_-]+)$") | .name) else null end) as $block_anchor
                   | (if ($val | test("^&[a-zA-Z0-9_-]+\\s")) then ($val | capture("^&(?<name>[a-zA-Z0-9_-]+)\\s+(?<rest>.+)$")) else null end) as $scalar_anchor
                   | (if ($val | test("^\\*[a-zA-Z0-9_-]+$")) then ($val | capture("^\\*(?<name>[a-zA-Z0-9_-]+)$") | .name) else null end) as $alias_name
                   | if $block_anchor != null then
                       (.stack[0].obj[$line.key] = {}
                        | .stack = ([{obj: .stack[0].obj[$line.key], indent: $line.indent, key: $line.key, anchor: $block_anchor}] + .stack)
                        | .last_key = $line.key)
                     elif $scalar_anchor != null then
                       (($scalar_anchor.rest | coerce_value) as $scalar_val
                        | .anchors[$scalar_anchor.name] = $scalar_val
                        | .stack[0].obj[$line.key] = $scalar_val
                        | .last_key = $line.key
                        | (if (.stack | length) > 1 and .stack[0].key != null then reduce range(0; .stack | length - 1) as $i (.; .stack[$i + 1].obj[.stack[$i].key] = .stack[$i].obj) else . end))
                     elif $alias_name != null then
                       (if $line.key == "<<" then
                          .stack[0].obj = (.stack[0].obj + (.anchors[$alias_name] // {}))
                        else
                          .stack[0].obj[$line.key] = (.anchors[$alias_name] // null)
                          | .last_key = $line.key
                        end
                        | (if (.stack | length) > 1 and .stack[0].key != null then reduce range(0; .stack | length - 1) as $i (.; .stack[$i + 1].obj[.stack[$i].key] = .stack[$i].obj) else . end))
                     else
                       .stack[0].obj[$line.key] = ($line.value | coerce_value)
                       | .last_key = $line.key
                       | (if (.stack | length) > 1 and .stack[0].key != null then reduce range(0; .stack | length - 1) as $i (.; .stack[$i + 1].obj[.stack[$i].key] = .stack[$i].obj) else . end)
                     end
                 end
            elif $line.type == "list_item" then
              ($line.value | coerce_list_item_value) as $item_val
              | (if (.stack | length) > 1 then .stack[1].obj[$state2.last_key] else .stack[0].obj[$state2.last_key] end) as $cur
              | if (.stack | length) > 1 then
                  .stack[1].obj[$state2.last_key] = (if $cur == null or ($cur | type) == "object" and ($cur | keys | length) == 0 then [$item_val] else $cur + [$item_val] end)
                else
                  .stack[0].obj[$state2.last_key] = (if $cur == null or ($cur | type) == "object" and ($cur | keys | length) == 0 then [$item_val] else $cur + [$item_val] end)
                end
              | (if (.stack | length) > 1 then .stack = .stack[1:] else . end)
              | .last_key = $state2.last_key
            else
              .
            end
        end
    end;

def parse_yaml:
  (if type == "string" then . else "" end) as $raw
  | $raw | slog("debug"; "parse_yaml_start"; {"lines": ($raw | split("\n") | length)})
  | parsed_lines as $lines
  | reduce $lines[] as $line (
      { stack: [{obj: {}, indent: -1, key: null}], last_key: null, root_is_list: false, block_scalar: null, anchors: {} };
      _process_line($line)
    )
  | (if .block_scalar != null then _finalize_block else . end)
  | if .root_is_list then .stack[1].obj + [.stack[0].obj] else .stack[.stack | length - 1].obj end;

# Convenience: parse YAML string and emit JSON
def parse_yaml_string:
  parse_yaml;
