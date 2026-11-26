#!/bin/sh
# Install or update pllab-accounts on pllab-server. Run as root from the repository.
#   sudo sh server/install.sh            install the sync timer and key lookup
#   sudo sh server/install.sh --harden   also turn off password and root SSH login
set -eu

here=$(cd "$(dirname "$0")" && pwd)
prefix=/opt/pllab-accounts
harden=no
[ "${1:-}" = "--harden" ] && harden=yes

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
python3 -c 'import jwt, cryptography' 2>/dev/null || apt-get install -y python3-jwt python3-cryptography

getent group pllab-members >/dev/null || groupadd pllab-members
getent passwd pllab-keys >/dev/null || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin pllab-keys

install -d -o root -g root -m 0755 "$prefix" "$prefix/bin" "$prefix/data" "$prefix/data/keys"
install -o root -g root -m 0755 "$here/pllab_accounts.py" "$prefix/bin/pllab-accounts"

install -d -o root -g root -m 0755 /etc/pllab-accounts
if [ ! -e /etc/pllab-accounts/config.json ]; then
  install -o root -g root -m 0644 "$here/config.example.json" /etc/pllab-accounts/config.json
  echo "created /etc/pllab-accounts/config.json; set app_id before enabling the timer"
fi

sudoers=$(mktemp)
echo '%pllab-members ALL=(ALL:ALL) NOPASSWD: ALL' > "$sudoers"
visudo -cqf "$sudoers"
install -o root -g root -m 0440 "$sudoers" /etc/sudoers.d/pllab-members
rm -f "$sudoers"

install -o root -g root -m 0644 "$here/sshd/10-pllab-accounts.conf" /etc/ssh/sshd_config.d/
if [ "$harden" = yes ]; then
  install -o root -g root -m 0644 "$here/sshd/05-pllab-hardening.conf" /etc/ssh/sshd_config.d/
fi
sshd -t

if [ -d /run/systemd/system ]; then
  install -o root -g root -m 0644 "$here/systemd/pllab-accounts.service" "$here/systemd/pllab-accounts.timer" /etc/systemd/system/
  systemctl daemon-reload
  systemctl try-reload-or-restart ssh.service
  if grep -q '"app_id": null' /etc/pllab-accounts/config.json; then
    echo "timer not enabled: app_id is not set"
  else
    systemctl enable --now pllab-accounts.timer
  fi
fi
echo "pllab-accounts installed"
