#!/usr/bin/env bash
# Verify the live chain on the HOST:  Hermes gateway -> oracle router :8090 -> hermes proxy :8645 -> Nous.
#
#   bash verify_live.sh                 # free checks only (status, model lists, health)
#   bash verify_live.sh --spend-tokens  # + two tiny real completions (~200 tokens total, < $0.0001)
set -uo pipefail

ROUTER="${ORACLE_ROUTER_URL:-http://127.0.0.1:8090/v1}"
PROXY="${HERMES_PROXY_URL:-http://127.0.0.1:8645/v1}"
pass=0; fail=0
ok()  { printf '  [OK]   %s\n' "$*"; pass=$((pass+1)); }
bad() { printf '  [FAIL] %s\n' "$*"; fail=$((fail+1)); }

printf '1) hermes proxy status\n'
if hermes proxy status 2>&1 | sed 's/^/       /'; then :; fi

printf '2) upstream proxy model list (%s)\n' "$PROXY"
if n=$(curl -fsS --max-time 10 "$PROXY/models" | python3 -c 'import json,sys;print(len(json.load(sys.stdin).get("data",[])))' 2>/dev/null); then
  ok "hermes proxy answers /models ($n models)"
else bad "hermes proxy not reachable — systemctl --user status hermes-subscription-proxy"; fi

printf '3) router health (%s)\n' "$ROUTER"
health=$(curl -fsS --max-time 10 "$ROUTER/health" 2>/dev/null)
if [[ -n "$health" ]] && python3 -c 'import json,sys;h=json.loads(sys.argv[1]);sys.exit(0 if h["status"]=="ok" else 1)' "$health"; then
  ok "router healthy: $(python3 -c 'import json,sys;h=json.loads(sys.argv[1]);print(h["registry"])' "$health")"
else bad "router not healthy: ${health:-no response} — journalctl --user -u oracle-router -n 50"; fi

if [[ "${1:-}" != "--spend-tokens" ]]; then
  printf '\nFree checks: %d ok, %d failed. Add --spend-tokens for the real end-to-end completions.\n' "$pass" "$fail"
  exit $(( fail > 0 ))
fi

printf '4) real non-stream completion via oracle/eco (max_tokens 16)\n'
resp=$(curl -sS --max-time 120 -D /tmp/oracle_headers.txt "$ROUTER/chat/completions" -H 'Content-Type: application/json' \
  -H 'x-hermes-session-id: verify-live' \
  -d '{"model":"oracle/eco","max_tokens":16,"messages":[{"role":"user","content":"Reply with the single word: ok"}]}')
model=$(grep -i '^x-oracle-selected-model:' /tmp/oracle_headers.txt | tr -d '\r' | cut -d' ' -f2)
if python3 - "$resp" <<'EOF'
import json, sys
r = json.loads(sys.argv[1])
msg = r["choices"][0]["message"].get("content")
print("       upstream id:", r.get("id"), "| model:", r.get("model"), "| usage:", r.get("usage"), "| content:", repr(msg))
sys.exit(0 if r.get("id") and r.get("usage") else 1)
EOF
then ok "real completion through router (selected: $model)"; else bad "completion failed: ${resp:0:300}"; fi

printf '5) real streaming tool call via oracle/eco\n'
stream=$(curl -sS -N --max-time 120 "$ROUTER/chat/completions" -H 'Content-Type: application/json' \
  -d '{"model":"oracle/eco","stream":true,"max_tokens":64,"tool_choice":"required",
       "tools":[{"type":"function","function":{"name":"ping","description":"Health check","parameters":{"type":"object","properties":{},"required":[]}}}],
       "messages":[{"role":"user","content":"Call the ping tool now."}]}')
if grep -q '"tool_calls"' <<<"$stream" && grep -q 'data: \[DONE\]' <<<"$stream"; then
  ok "SSE stream with tool_calls passed through"
else bad "no streamed tool_calls: ${stream:0:300}"; fi

printf '6) learning state\n'
curl -fsS --max-time 10 "$ROUTER/router/learning" | python3 -c 'import json,sys;d=json.load(sys.stdin);print("       signals:",d["signal_counts"],"| floors:",d["floors"])'

printf '\nEnd-to-end: %d ok, %d failed. Check Portal usage/billing for the two requests above.\n' "$pass" "$fail"
exit $(( fail > 0 ))
