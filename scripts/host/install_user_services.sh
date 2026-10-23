#!/usr/bin/env bash
# Install the Hermes subscription proxy (:8645) and the oracle router (:8090) as systemd *user*
# services on the HOST (next to the Hermes gateway). Dry-run by default.
#
#   bash install_user_services.sh            # show what would happen, change nothing
#   bash install_user_services.sh --apply    # install / update and (re)start both services
#
# Security: the router code is copied from the agent sandbox into a host-owned directory at a
# pinned git commit. Later edits inside the sandbox do NOT affect the running host service until
# a human re-runs this script with --apply.
set -euo pipefail

MODE="${1:---dry-run}"
REPO_SRC="${ORACLE_ROUTER_REPO:-$HOME/.hermes/sandboxes/docker/default/home/ai_browser_farm}"
BASE="${ORACLE_ROUTER_HOME:-$HOME/.local/share/oracle-router}"
APP="$BASE/app"
DATA="$BASE/data"
UNIT_DIR="$HOME/.config/systemd/user"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ -d "$REPO_SRC/src/router" ]] || die "router source not found at $REPO_SRC (set ORACLE_ROUTER_REPO)"
HERMES_BIN="$(command -v hermes)" || die "hermes not on PATH"
PYTHON_BIN="$(command -v python3)" || die "python3 not on PATH"
command -v systemctl >/dev/null || die "systemctl not available"

COMMIT="unknown"
if command -v git >/dev/null && git -C "$REPO_SRC" rev-parse HEAD >/dev/null 2>&1; then
  COMMIT="$(git -C "$REPO_SRC" rev-parse --short HEAD)"
  if [[ -n "$(git -C "$REPO_SRC" status --porcelain -- src)" ]]; then
    die "uncommitted changes under src/ in $REPO_SRC — commit or stash before deploying"
  fi
fi

PROXY_UNIT="[Unit]
Description=Hermes subscription proxy (Nous Portal, loopback only)
After=network-online.target

[Service]
ExecStart=$HERMES_BIN proxy start --provider nous --host 127.0.0.1 --port 8645
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"

ROUTER_UNIT="[Unit]
Description=Oracle router (OpenAI-compatible, loopback only) — commit $COMMIT
After=hermes-subscription-proxy.service network-online.target
Wants=hermes-subscription-proxy.service

[Service]
WorkingDirectory=$APP
ExecStart=$PYTHON_BIN -m src.cli serve --port 8090 --db-dir $DATA --nous-proxy-url http://127.0.0.1:8645/v1
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$DATA
MemoryMax=512M

[Install]
WantedBy=default.target
"

printf 'Source : %s (commit %s)\nApp    : %s\nData   : %s\nUnits  : %s\n\n' "$REPO_SRC" "$COMMIT" "$APP" "$DATA" "$UNIT_DIR"
if [[ "$MODE" != "--apply" ]]; then
  printf '%s\n' '--- hermes-subscription-proxy.service ---' "$PROXY_UNIT" '--- oracle-router.service ---' "$ROUTER_UNIT"
  printf 'DRY RUN: nothing changed. Re-run with --apply to install.\n'
  exit 0
fi

mkdir -p "$DATA" "$UNIT_DIR"
STAGE="$(mktemp -d "$BASE/app.stage.XXXX")"
if [[ "$COMMIT" != "unknown" ]]; then
  git -C "$REPO_SRC" archive HEAD src | tar -x -C "$STAGE"
else
  cp -a "$REPO_SRC/src" "$STAGE/src"
fi
printf '%s\n' "$COMMIT" > "$STAGE/DEPLOYED_COMMIT"
rm -rf "$APP.old"; [[ -d "$APP" ]] && mv "$APP" "$APP.old"
mv "$STAGE" "$APP"
chmod -R go-w "$APP"

printf '%s' "$PROXY_UNIT" > "$UNIT_DIR/hermes-subscription-proxy.service"
printf '%s' "$ROUTER_UNIT" > "$UNIT_DIR/oracle-router.service"
systemctl --user daemon-reload
systemctl --user enable --now hermes-subscription-proxy.service
systemctl --user enable oracle-router.service
systemctl --user restart oracle-router.service

for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:8090/v1/health >/dev/null 2>&1; then break; fi
  sleep 1
done
printf '\nHealth:\n'; curl -fsS --max-time 5 http://127.0.0.1:8090/v1/health || printf 'router not healthy yet: journalctl --user -u oracle-router -n 50\n'
printf '\n\nNext: bash %s/scripts/host/verify_live.sh\n' "$REPO_SRC"
printf 'Optional (keep services running while logged out): loginctl enable-linger %s\n' "${USER:-$(id -un)}"
