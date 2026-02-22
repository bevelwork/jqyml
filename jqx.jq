# jqx: build text from a template with {var_name}, <If>, <For>, and <Name /> components.
# Usage: echo '{"items":["a","b"]}' | jq --rawfile tmpl template.jqx -f jqx.jq
# With components: add --rawfile header header.jqx (and/or other component files); use <Header /> in template.
# - {identifier} is replaced by .identifier from the object.
# - <If name>content</If> is included only when .name is truthy. Nested <If> is supported.
# - <For iter list_key>content with {iter}</For> is repeated for each element of .list_key.
# - <Name /> includes the component template named Name (from $header etc.); component is processed with same vars.

# Return index in $s of the matching </If> for the block starting after an opening <If> at depth 1.
# $from is the index of the first character after the opening tag (after ">").
def find_matching_endif($s; $from):
  ($s[$from:] | index("</If>")) as $b
  | if $b == null then null
    else ($s[$from:] | index("<If ")) as $a
    | if $a == null or $b < $a then $from + $b
      else ($s[$from + $a + 4:] | index(">")) as $g
      | if $g == null then null
        else ($from + $a + 4 + $g + 1) as $inner_start
        | find_matching_endif($s; $inner_start) as $inner_end
        | if $inner_end == null then null
          else find_matching_endif($s; $inner_end + 5)
          end
        end
      end
    end;

# Expand the first <If name>content</If> block; include content only if $vars[name] is truthy.
def expand_one_if($vars):
  . as $t
  | ($t | index("<If ")) as $start
  | if $start == null then $t
    else ($t[$start:] | index(">")) as $tag_len
    | if $tag_len == null then $t
      else ($t[$start:($start + $tag_len + 1)] | capture("<If (?<name>[a-zA-Z0-9_]+)>")) as $m
      | if $m == null then $t
        else ($start + $tag_len + 1) as $content_start
        | find_matching_endif($t; $content_start) as $match_end
        | if $match_end == null then $t
          else $t[$content_start:$match_end] as $content
          | ($match_end + 5) as $after_start
          | $t[$after_start:] as $after
          | (if $vars[$m.name] then $content else "" end) as $replacement
          | $t[:$start] + $replacement + $after
          end
        end
      end
    end;

def expand_if($vars):
  expand_one_if($vars) as $next
  | if $next == . then . else $next | expand_if($vars) end;

# Expand the first <For var key>content</For> block; return expanded string or original if none.
def expand_one_for($vars):
  . as $t
  | ($t | index("<For ")) as $start
  | if $start == null then $t
    else ($t[$start:] | index(">")) as $tag_len
    | if $tag_len == null then $t
      else ($t[$start:($start + $tag_len + 1)] | capture("<For (?<var>[a-zA-Z0-9_]+) (?<key>[a-zA-Z0-9_]+)>")) as $m
      | if $m == null then $t
        else ($start + $tag_len + 1) as $content_start
        | ($t[$content_start:] | index("</For>")) as $content_len
        | if $content_len == null then $t
          else $t[$content_start:($content_start + $content_len)] as $content
          | ($content_start + $content_len + 6) as $after_start
          | $t[$after_start:] as $after
          | (($vars[$m.key] // []) | if type == "array" then . else [] end) as $list
          | ($list | map(. as $elem | $content | gsub("\\{" + $m.var + "\\}"; $elem | tostring)) | join("")) as $expanded
          | $t[:$start] + $expanded + $after
          end
        end
      end
    end;

# Expand all <For> blocks (repeat until no change).
def expand_for($vars):
  expand_one_for($vars) as $next
  | if $next == . then . else $next | expand_for($vars) end;

def substitute_vars($vars):
  reduce ([scan("\\{[a-zA-Z0-9_]+\\}")] | unique[]) as $ph (
    .;
    gsub($ph; ($vars[$ph[1:-1]] // "" | tostring))
  );

# Render a component string with the same pipeline (if/for/vars)
def render_component($comp; $vars):
  $comp | expand_if($vars) | expand_for($vars) | substitute_vars($vars);

# Escape replacement string for gsub (so & and \ are literal)
def escape_replacement:
  gsub("\\\\"; "\\\\\\\\") | gsub("&"; "\\\\&");

# Find first <Name /> or <Name/> in $t; return {pos, len, name} or null
def _first_component_tag($t; $components):
  ($components | keys) as $names
  | [ $names[] as $name
      | ($t | index("<" + $name + " />")) as $p1
      | ($t | index("<" + $name + "/>")) as $p2
      | (if $p1 != null and ($p2 == null or $p1 <= $p2) then { pos: $p1, len: (("<" + $name + " />") | length), name: $name }
        elif $p2 != null then { pos: $p2, len: (("<" + $name + "/>") | length), name: $name }
        else null end) ]
  | map(select(. != null))
  | if length == 0 then null else min_by(.pos) end;

# Replace the first <Name /> where Name is in $components
def expand_one_include($vars; $components):
  . as $t
  | _first_component_tag($t; $components) as $m
  | if $m == null then $t
    else ($components[$m.name] | render_component(.; $vars) | escape_replacement) as $repl
    | $t[0:$m.pos] + $repl + $t[$m.pos + $m.len:]
    end;

def expand_includes($vars; $components):
  if ($components | keys | length) == 0 then .
  else expand_one_include($vars; $components) as $next
  | if $next == . then . else $next | expand_includes($vars; $components) end
  end;

# Build components map from rawfiles ($header -> "Header"). Pass empty.jqx when no components needed.
def components_from_rawfiles:
  (if ($header | length) > 0 then { "Header": $header } else {} end);

. as $vars
| components_from_rawfiles as $components
| $tmpl
| expand_includes($vars; $components)
| expand_if($vars)
| expand_for($vars)
| substitute_vars($vars)
