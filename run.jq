include "log";
include "yaml";

# Parse YAML (supports anchors &name and aliases *name, merge <<: *name)
. | slog("info"; "convert_start"; {"input_bytes": (length)})
| parse_yaml
| slog("info"; "convert_ok"; {"top_level_keys": (keys | length)})
