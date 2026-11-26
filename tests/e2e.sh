#!/bin/sh
# End-to-end check in a throwaway container: real GitHub org data, real sshd.
#   PLLAB_TEST_USER  GitHub login whose key is $PLLAB_TEST_KEY (default: gh user)
#   PLLAB_TEST_KEY   private key registered on that GitHub account
set -eu
cd "$(dirname "$0")/.."
login=${PLLAB_TEST_USER:-$(gh api user -q .login)}
key=${PLLAB_TEST_KEY:-$HOME/.ssh/id_ed25519}
user=$(printf %s "$login" | tr 'A-Z' 'a-z')
name=pllab-accounts-e2e
port=22022

docker build -q -t "$name" -f tests/Dockerfile . >/dev/null
docker rm -f "$name" >/dev/null 2>&1 || true
docker run -d --name "$name" -p "127.0.0.1:$port:22" -e PLLAB_GITHUB_TOKEN="$(gh auth token)" "$name" >/dev/null
trap 'docker rm -f "$name" >/dev/null' EXIT
ct() { docker exec "$name" "$@"; }
sshc() { ssh -p "$port" -i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR "$@"; }
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; exit 1; }

ct sh -c 'printf "{\"org\":\"PLLab-Project\"}" > /etc/pllab-accounts/config.json'
ct sh -c 'useradd -m ghost && echo "{\"accounts\":{\"1\":{\"user\":\"ghost\",\"login\":\"ghost\",\"status\":\"active\"}}}" > /opt/pllab-accounts/data/accounts.json'

ct /opt/pllab-accounts/bin/pllab-accounts sync
ct id "$user" | grep -q pllab-members && pass "member account created in pllab-members" || fail "member account"
ct sh -c "chage -l ghost | grep -q 'Account expires.*1970'" && pass "departed member locked" || fail "lock"

sshc "$user@127.0.0.1" 'sudo -n true && id -un' | grep -qx "$user" && pass "key login and passwordless sudo" || fail "login"
eff=$(ct sshd -T)
echo "$eff" | grep -qx 'passwordauthentication no' && pass "password auth off" || fail "password auth"
echo "$eff" | grep -qx 'permitrootlogin no' && pass "root login off" || fail "root login"

out=$(ct runuser -u pllab-keys -- /opt/pllab-accounts/bin/pllab-accounts keys "$user")
[ -n "$out" ] && pass "keys command prints live keys as pllab-keys" || fail "keys output"
ct runuser -u pllab-keys -- /opt/pllab-accounts/bin/pllab-accounts keys ghost | grep -q . && fail "locked user got keys" || pass "locked user gets no keys"

ct sh -c 'printf "{\"org\":\"PLLab-Project\",\"api_base\":\"http://127.0.0.1:9\"}" > /etc/pllab-accounts/config.json'
sshc "$user@127.0.0.1" true && pass "login falls back to cached keys when GitHub is unreachable" || fail "cache fallback"

ct /opt/pllab-accounts/bin/pllab-accounts sync 2>/dev/null && fail "sync ran without GitHub" || pass "sync changes nothing without GitHub"
ct id "$user" >/dev/null && pass "accounts kept after failed sync" || fail "accounts kept"

home=$(mktemp -d)
trap 'docker rm -f "$name" >/dev/null; rm -rf "$home"' EXIT
mkdir -m 700 "$home/.ssh"
cp "$key" "$home/.ssh/pllab_ed25519"
cp "$key.pub" "$home/.ssh/pllab_ed25519.pub"
printf 'Host other\n    HostName example.com\n' > "$home/.ssh/config"
ghdir=${GH_CONFIG_DIR:-$HOME/.config/gh}
run_setup() {
  HOME=$home GH_CONFIG_DIR=$ghdir PLLAB_HOST=127.0.0.1 PLLAB_PORT=$port PLLAB_PROXY=none \
    PLLAB_HOSTKEY="[127.0.0.1]:$port $(ct cat /etc/ssh/ssh_host_ed25519_key.pub | cut -d' ' -f1,2)" sh client/setup.sh
}
ct sh -c 'printf "{\"org\":\"PLLab-Project\"}" > /etc/pllab-accounts/config.json'
run_setup </dev/null >/dev/null && pass "client setup reaches the server" || fail "client setup"
run_setup </dev/null >/dev/null && pass "client setup is safe to rerun" || fail "client rerun"
[ "$(grep -c '>>> pllab-onboard' "$home/.ssh/config")" = 1 ] && grep -q '^Host other' "$home/.ssh/config" && pass "ssh config keeps one managed block and other hosts" || fail "ssh config"
HOME=$home ssh -F "$home/.ssh/config" -o BatchMode=yes pllab id -un | grep -qx "$user" && pass "ssh pllab logs in as $user" || fail "ssh pllab"
