# Logging helpers for the jq engine. Output goes to stderr via debug (one JSON object per slog call).
# Usage: include "log"; ... | log("message") | ...   or   ... | slog("info"; "msg"; {"key": "value"}) | ...
# The input value is passed through unchanged so you can insert logging in a pipeline.

# Simple message to stderr; pass through input.
def log($msg):
  . as $in
  | (if $msg | type == "string" then $msg else ($msg | tostring) end | debug)
  | $in;

# Structured log (slog-style): level, message, and optional key-value attrs. Emits one JSON object to stderr.
# Level is typically "info", "warn", "error", "debug".
# Attrs can be {} or omitted for none.
def slog($level; $msg; $attrs):
  . as $in
  | (({level: $level, msg: $msg} + ($attrs // {})) | tostring | debug)
  | $in;

# Overload: slog(level; msg) with no attrs
def slog($level; $msg):
  slog($level; $msg; {});
