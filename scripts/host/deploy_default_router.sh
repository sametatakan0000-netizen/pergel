#!/usr/bin/env bash
# One idempotent host step: deploy the current committed router, verify it, and write a
# receipt into the sandbox-shared repo so the agent can read the result.
#   bash scripts/host/deploy_default_router.sh
set -uo pipefail
REPO="$HOME/.hermes/sandboxes/docker/default/home/ai_browser_farm"
LOG="$REPO/host_default_router.log"
{
  echo "== $(date -Iseconds) deploy"
  bash "$REPO/scripts/host/install_user_services.sh" --apply 2>&1
  echo "== restart"
  systemctl --user restart oracle-router.service 2>&1
  sleep 3
  echo "== units"
  systemctl --user is-active oracle-router.service hermes-subscription-proxy.service hermes-gateway.service 2>&1
  echo "== /v1/models"
  curl -s -m 5 http://127.0.0.1:8090/v1/models; echo
  echo "== /v1/health"
  curl -s -m 5 http://127.0.0.1:8090/v1/health | head -c 300; echo
  echo "== deployed commit"
  cat "$HOME/.local/share/oracle-router/app/DEPLOYED_COMMIT" 2>/dev/null; echo
  echo "== hermes default model"
  hermes config show 2>/dev/null | grep -m1 "Model:"
  echo "== done"
} 2>&1 | tee "$LOG"
