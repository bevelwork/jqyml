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

