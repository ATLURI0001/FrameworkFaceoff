-- wrk Lua script for the json-tls profile.
-- Rotates through the same 7 (count, m) pairs used by the plain `json` profile
-- (plaintext) and `json-comp` (compressed). No Accept-Encoding header here —
-- this test measures JSON serialization + HTTP/1.1 over TLS, not compression.
-- Target host/port is passed on the wrk command line (e.g. https://localhost:8081).

local pairs_list = {
  { path = "/json/1?m=3" },
  { path = "/json/5?m=7" },
  { path = "/json/10?m=2" },
  { path = "/json/15?m=5" },
  { path = "/json/25?m=4" },
  { path = "/json/40?m=8" },
  { path = "/json/50?m=6" },
}

local counter = 0

request = function()
  counter = counter + 1
  local p = pairs_list[((counter - 1) % #pairs_list) + 1]
  return wrk.format("GET", p.path)
end
