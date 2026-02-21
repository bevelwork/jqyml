# Route parsing: request -> { action, body? }
# Input: { method, path, body? }  (path may include query string)
# Output: { action: "index" | "index_old" | "convert" | "not_found", body?: string }

(.path | split("?")[0]) as $path
| if .method == "GET" and ($path == "/" or $path == "/index.html") then
    { action: "index" }
  elif .method == "GET" and $path == "/old" then
    { action: "index_old" }
  elif .method == "POST" and $path == "/" then
    { action: "convert", body: (.body // "") }
  else
    { action: "not_found" }
  end
