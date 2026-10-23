#!/usr/bin/env bash
# One-shot host setup + live verification. Run ON THE HOST (e.g. over remote desktop):
#
#   bash ~/.hermes/sandboxes/docker/default/home/ai_browser_farm/scripts/host/remote_quickstart.sh
#
# Steps: install/refresh services (pinned commit) -> free checks -> 2 tiny real requests
# (< $0.0001) -> register the `oracle-router` provider (main model untouched).
# Full output is written to host_quickstart.log next to the repo, which the sandboxed agent can
# read directly — no copy/paste needed.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG="$REPO/host_quickstart.log"

{
  printf '=== oracle-router quickstart %s ===\n' "$(date -Is)"
  bash "$REPO/scripts/host/install_user_services.sh" --apply || { echo "INSTALL FAILED"; exit 1; }
  echo
  bash "$REPO/scripts/host/verify_live.sh" --spend-tokens; verify_rc=$?
  echo
  if [[ $verify_rc -eq 0 ]]; then
    ORACLE_ROUTER_APPLY=1 bash "$REPO/scripts/hermes_full_optimize_commands.sh"
    printf '\nDONE. In Telegram, open a NEW chat/session and send:\n  /model custom:oracle-router:oracle/auto\n'
  else
    printf 'Verification failed (rc=%s): provider NOT registered. Logs:\n' "$verify_rc"
    journalctl --user -u oracle-router -n 30 --no-pager 2>&1 | sed 's/^/  /'
    journalctl --user -u hermes-subscription-proxy -n 30 --no-pager 2>&1 | sed 's/^/  /'
  fi
} 2>&1 | tee "$LOG"
printf '\nLog saved: %s\n' "$LOG"
