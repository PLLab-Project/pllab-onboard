#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
login=${PLLAB_TEST_USER:-$(gh api user -q .login)}
key=${PLLAB_TEST_KEY:-$HOME/.ssh/id_ed25519}
user=$(printf %s "$login" | tr '[:upper:]' '[:lower:]')
name=pllab-accounts-e2e
port=22022
home=$(mktemp -d)
ghdir=${GH_CONFIG_DIR:-$HOME/.config/gh}

docker build -q -t "$name" -f tests/Dockerfile . >/dev/null
docker rm -f "$name" >/dev/null 2>&1 || true
docker run -d --name "$name" -p "127.0.0.1:$port:22" -e PLLAB_GITHUB_TOKEN="$(gh auth token)" "$name" >/dev/null
trap 'docker rm -f "$name" >/dev/null; rm -rf "$home"' EXIT
ct() { docker exec "$name" "$@"; }
sshc() { ssh -p "$port" -i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR "$@"; }
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; exit 1; }
config() { ct sh -c "printf '%s' '$1' > /etc/pllab-accounts/config.json"; }
keys_as_sshd() { ct runuser -u pllab-keys -- /opt/pllab-accounts/bin/pllab-accounts keys "$1"; }

config '{"org":"PLLab-Project"}'
ct sh -c 'useradd -m ghost && echo "{\"accounts\":{\"1\":{\"user\":\"ghost\",\"login\":\"ghost\",\"status\":\"active\"}}}" > /opt/pllab-accounts/data/accounts.json'

ct /opt/pllab-accounts/bin/pllab-accounts sync 2>/dev/null
ct id "$user" | grep -q pllab-members && pass "member account created in pllab-members" || fail "member account"
ct sh -c "chage -l ghost | grep -q 'Account expires.*1970'" && pass "departed member locked" || fail "lock"

sshc "$user@127.0.0.1" 'sudo -n true && id -un' | grep -qx "$user" && pass "key login and passwordless sudo" || fail "login"
eff=$(ct sshd -T)
echo "$eff" | grep -qx 'passwordauthentication no' && pass "password auth off" || fail "password auth"
echo "$eff" | grep -qx 'permitrootlogin no' && pass "root login off" || fail "root login"

[ -n "$(keys_as_sshd "$user")" ] && pass "keys command prints cached keys as pllab-keys" || fail "keys output"
[ -z "$(keys_as_sshd ghost)" ] && pass "locked user gets no keys" || fail "locked user got keys"
[ -z "$(keys_as_sshd ../data/accounts.json)" ] && pass "keys command ignores odd user names" || fail "odd user name"

ct touch -d '2 days ago' "/opt/pllab-accounts/data/keys/$user"
[ -z "$(keys_as_sshd "$user")" ] && pass "keys older than 24h are refused" || fail "stale keys accepted"
ct /opt/pllab-accounts/bin/pllab-accounts sync 2>/dev/null
[ -n "$(keys_as_sshd "$user")" ] && pass "next sync refreshes the cache" || fail "cache refresh"

config '{"org":"PLLab-Project","api_base":"http://127.0.0.1:9"}'
ct /opt/pllab-accounts/bin/pllab-accounts sync 2>/dev/null && fail "sync ran without GitHub" || pass "sync changes nothing without GitHub"
sshc "$user@127.0.0.1" true && pass "login keeps working while GitHub is unreachable" || fail "login during outage"
config '{"org":"PLLab-Project"}'

mkdir -m 700 "$home/.ssh"
cp "$key" "$home/.ssh/pllab_ed25519"
cp "$key.pub" "$home/.ssh/pllab_ed25519.pub"
printf 'ServerAliveInterval 42\n\nHost other\n    HostName example.com\n' > "$home/.ssh/config"
hostkey="[127.0.0.1]:$port $(ct cat /etc/ssh/ssh_host_ed25519_key.pub | cut -d' ' -f1,2)"
run_setup() {
  HOME=$home GH_CONFIG_DIR=$ghdir PLLAB_HOST=127.0.0.1 PLLAB_PORT=$port PLLAB_PROXY=none PLLAB_HOSTKEY=$hostkey \
    sh client/setup.sh </dev/null >/dev/null
}
run_setup && pass "client setup reaches the server" || fail "client setup"
run_setup && pass "client setup is safe to rerun" || fail "client rerun"
[ "$(grep -c '>>> pllab-onboard' "$home/.ssh/config")" = 1 ] && pass "ssh config keeps one managed block" || fail "managed block"
ssh -F "$home/.ssh/config" -G other | grep -qx 'serveraliveinterval 42' && pass "global ssh options still apply to other hosts" || fail "global options"
ssh -F "$home/.ssh/config" -o BatchMode=yes pllab id -un | grep -qx "$user" && pass "ssh pllab logs in as $user" || fail "ssh pllab"
