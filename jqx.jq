# jqx: build text from a template with {var_name} placeholders and <For var key>...</For>.
# Usage: echo '{"items":["a","b"]}' | jq --rawfile tmpl template.jqx -f jqx.jq
# - {identifier} is replaced by .identifier from the object.
# - <For iter list_key>content with {iter}</For> is repeated for each element of .list_key.

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

. as $vars
| $tmpl
| expand_for($vars)
| substitute_vars($vars)
