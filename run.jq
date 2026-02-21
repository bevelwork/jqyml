include "yaml";

# Reject YAML anchors: &name and *alias (error goes to stderr, exit non-zero)
. as $input
| if ($input | test("&[a-zA-Z0-9_-]+|\\*[a-zA-Z0-9_-]+")) then
    error("you're an idiot... don't use anchors")
  else
    $input | parse_yaml
  end
