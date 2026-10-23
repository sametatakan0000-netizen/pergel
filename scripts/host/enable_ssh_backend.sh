#!/usr/bin/env bash
# Switch Hermes' terminal backend from Docker to SSH-over-loopback so the agent can run host
# commands itself (no more copy/paste). Idempotent. Log is written into the repo so the
# sandboxed agent can read it:  <repo>/host_ssh_setup.log
#
# Safety design:
#  * dedicated ed25519 key, restricted in authorized_keys: from=loopback only, no forwarding
#  * the config is switched ONLY after a real SSH login test succeeded
#  * config.yaml backup + one-line rollback printed at the end
#  * sshd is only hardened (no password auth) if THIS script installed it
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LOG="$REPO/host_ssh_setup.log"
exec > >(tee "$LOG") 2>&1

KEY="$HOME/.ssh/hermes_agent_key"
HHOME="${HERMES_HOME:-$HOME/.hermes}"
die() { echo "FAIL: $*"; exit 1; }
step() { printf '\n== %s\n' "$*"; }

step "0. preflight ($(date -Is))"
command -v hermes >/dev/null || die "hermes not on PATH (run from the host user shell)"
echo "user=$(id -un) home=$HOME hermes_home=$HHOME repo=$REPO"
echo "current backend: $(hermes config get terminal.backend 2>&1 | tail -1)"

step "1. sshd"
INSTALLED_NOW=0
if ! command -v sshd >/dev/null && [ ! -x /usr/sbin/sshd ]; then
  echo "openssh-server missing -> installing (sudo password may be requested)"
  sudo apt-get install -y openssh-server || die "apt install openssh-server failed"
  INSTALLED_NOW=1
fi
sudo systemctl enable --now ssh 2>&1 || sudo systemctl enable --now ssh.socket 2>&1 || die "cannot start ssh"
if [ "$INSTALLED_NOW" = 1 ]; then
  printf 'PasswordAuthentication no\nPermitRootLogin no\n' | sudo tee /etc/ssh/sshd_config.d/50-hermes-hardening.conf >/dev/null
  sudo systemctl reload ssh 2>/dev/null || sudo systemctl restart ssh 2>/dev/null || true
  echo "fresh install: password auth disabled (key-only)"
fi
echo "active: $(systemctl is-active ssh 2>&1) / socket: $(systemctl is-active ssh.socket 2>&1)"
echo "listening:"; ss -ltn 2>/dev/null | grep ':22 ' || echo "  (nothing on :22!)"

step "2. dedicated key (loopback-only)"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
[ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "hermes-agent-terminal" -f "$KEY" || die "keygen"
PUB="$(cat "$KEY.pub")"
BLOB="$(echo "$PUB" | awk '{print $2}')"
touch "$HOME/.ssh/authorized_keys" && chmod 600 "$HOME/.ssh/authorized_keys"
if grep -q "$BLOB" "$HOME/.ssh/authorized_keys"; then echo "key already authorized"; else
  echo "from=\"127.0.0.1,::1\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding $PUB" >> "$HOME/.ssh/authorized_keys"
  echo "key authorized (loopback only)"
fi

step "3. login test (must pass before any config change)"
OUT="$(ssh -i "$KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
      -o ConnectTimeout=8 "$(id -un)@127.0.0.1" 'echo ssh-ok; whoami; pwd; command -v systemctl' 2>&1)" \
  || { echo "$OUT"; die "SSH login test failed — config NOT changed, backend still docker"; }
echo "$OUT"

step "4. switch backend"
cp -a "$HHOME/config.yaml" "$HHOME/config.yaml.bak-before-ssh" && echo "backup: $HHOME/config.yaml.bak-before-ssh"
hermes config set terminal.backend ssh || die "config set backend"
hermes config set TERMINAL_SSH_HOST 127.0.0.1 || die "set host"
hermes config set TERMINAL_SSH_USER "$(id -un)" || die "set user"
hermes config set TERMINAL_SSH_KEY "$KEY" || die "set key"
echo "backend now: $(hermes config get terminal.backend 2>&1 | tail -1)"

step "5. boot-survival + read-only diagnostics (for cleanup/remote topics)"
loginctl enable-linger "$(id -un)" 2>&1 || sudo loginctl enable-linger "$(id -un)" 2>&1
loginctl show-user "$(id -un)" -p Linger 2>&1
for u in oracle-router hermes-proxy; do printf '%s: ' "$u"; systemctl --user is-enabled "$u.service" 2>&1; done
hermes gateway status 2>&1 | head -8
hermes sessions stats 2>&1 | head -15

step "DONE"
cat <<EOF
Next (you): send /restart in Telegram, then /new.
Agent will verify with a host command and update cron paths (repo path changes: see below).
Repo on host: $REPO
ROLLBACK (any time, host shell):  hermes config set terminal.backend docker   # then /restart
EOF
