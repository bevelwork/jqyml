# state.jq: validate POST /state request; if valid, output new_state with .counter incremented.
# Input: { request: { method, path, headers: {}, body: {} }, current_state: {} }
# Output: { valid: true, new_state: {...} } or { valid: false, status: 400, message: "..." }
# Validation: Content-Type header present and application/json; body.counter == 1.

.request as $req
| ($req.headers["Content-Type"] // $req.headers["content-type"] // "") as $ct
| ($req.body | type == "object" and .counter == 1) as $body_ok
| ($ct != null and $ct != "" and ($ct | test("application/json"))) as $ct_ok
| if ($body_ok | not) then
    { valid: false, status: 400, message: "body must be JSON object with counter == 1" }
  elif ($ct_ok | not) then
    { valid: false, status: 400, message: "Content-Type must be application/json" }
  else
    { valid: true, new_state: (.current_state | .counter += 1) }
  end
