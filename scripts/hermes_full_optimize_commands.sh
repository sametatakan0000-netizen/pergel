#!/usr/bin/env bash
set -euo pipefail
# Deliberately NOT a full-optimization installer: only registers the named custom endpoint.
# Run on the machine that runs the Hermes gateway, not inside an unrelated Docker sandbox.
if [[ "${ORACLE_ROUTER_APPLY:-}" != "1" ]]; then
  printf '%s\n' 'DRY RUN ONLY. Nothing changed. First verify both local services and a real Nous response.'
  printf '%s\n' 'To apply after manual review: ORACLE_ROUTER_APPLY=1 bash scripts/hermes_full_optimize_commands.sh'
  exit 0
fi
for url in http://127.0.0.1:8645/v1/models http://127.0.0.1:8090/v1/models; do
  curl --fail --silent --show-error --max-time 5 "$url" >/dev/null
 done
hermes config set providers.oracle-router.api http://127.0.0.1:8090/v1
hermes config set providers.oracle-router.transport chat_completions
hermes config set providers.oracle-router.api_key local-router   # placeholder, not a secret: router is loopback-only
hermes config set providers.oracle-router.session_affinity_header x-hermes-session-id
hermes config set providers.oracle-router.catalog_provider nous
hermes config set providers.oracle-router.default_model oracle/auto
printf '%s\n' 'Endpoint registered. Main model unchanged; test explicitly in a NEW Hermes session.'
