#!/bin/sh
set -eu

ORG=PLLab-Project
HOST=${PLLAB_HOST:-ssh.pl-official.site}
ALIAS=${PLLAB_ALIAS:-pllab}
HOSTKEY=${PLLAB_HOSTKEY:-"ssh.pl-official.site ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEYfMUnsI9YTzVvGLFVO85uC/ZdIggHcijwbS7duiD+X"}
SSH_DIR=$HOME/.ssh
KEY=${PLLAB_KEY:-$SSH_DIR/pllab_ed25519}
BIN=$HOME/.local/bin
BEGIN='# >>> pllab-onboard >>>'
END='# <<< pllab-onboard <<<'

step() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

arch() {
  case $(uname -m) in
    x86_64 | amd64) echo amd64 ;;
    aarch64 | arm64) echo arm64 ;;
    *) die "unsupported CPU $(uname -m)" ;;
  esac
}

install_tools() {
  step "Check ssh, cloudflared and gh"
  have ssh && have ssh-keygen || die "OpenSSH client is missing. Install it with your package manager."
  mkdir -p "$BIN"
  PATH=$BIN:$PATH
  export PATH
  mac=no
  [ "$(uname -s)" = Darwin ] && mac=yes
  for tool in cloudflared gh; do
    have "$tool" && continue
    if [ "$mac" = yes ] && have brew; then
      brew install "$tool"
    else
      download_"$tool" "$mac"
    fi
  done
}

download_cloudflared() {
  base=https://github.com/cloudflare/cloudflared/releases/latest/download
  if [ "$1" = yes ]; then
    curl -fsSL "$base/cloudflared-darwin-$(arch).tgz" | tar -xz -C "$BIN" cloudflared
  else
    curl -fsSL "$base/cloudflared-linux-$(arch)" -o "$BIN/cloudflared"
  fi
  chmod +x "$BIN/cloudflared"
}

download_gh() {
  version=$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p')
  base=https://github.com/cli/cli/releases/download/v$version
  tmp=$(mktemp -d)
  if [ "$1" = yes ]; then
    curl -fsSL "$base/gh_${version}_macOS_$(arch).zip" -o "$tmp/gh.zip"
    unzip -q "$tmp/gh.zip" -d "$tmp"
  else
    curl -fsSL "$base/gh_${version}_linux_$(arch).tar.gz" | tar -xz -C "$tmp"
  fi
  cp "$tmp"/gh_*/bin/gh "$BIN/gh"
  chmod +x "$BIN/gh"
  rm -rf "$tmp"
}

github_login() {
  step "Sign in to GitHub"
  if ! gh auth status --hostname github.com >/dev/null 2>&1; then
    gh auth login --hostname github.com --git-protocol https --web --scopes admin:public_key
  fi
  LOGIN=$(gh api user --jq .login)
  echo "GitHub user: $LOGIN"
}

join_org() {
  step "Check $ORG membership"
  state=$(gh api "user/memberships/orgs/$ORG" --jq .state 2>/dev/null || echo none)
  if [ "$state" = pending ]; then
    gh api --method PATCH "user/memberships/orgs/$ORG" -f state=active >/dev/null 2>&1 && state=active
  fi
  if [ "$state" = pending ]; then
    echo "Accept the invitation in a browser: https://github.com/orgs/$ORG/invitation"
    i=0
    while [ "$state" != active ]; do
      i=$((i + 1))
      [ "$i" -gt 60 ] && die "The invitation is still not accepted."
      sleep 10
      state=$(gh api "user/memberships/orgs/$ORG" --jq .state 2>/dev/null || echo none)
    done
  fi
  [ "$state" = active ] || die "$LOGIN is not in $ORG. Ask an organization owner to invite $LOGIN."
  echo "Member of $ORG"
}

register_key() {
  step "Register this computer's SSH key on GitHub"
  mkdir -p "$SSH_DIR"
  chmod 700 "$SSH_DIR"
  [ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "pllab $LOGIN@$(hostname)" -f "$KEY"
  pub=$(awk '{print $2}' "$KEY.pub")
  if curl -fsSL "https://github.com/$LOGIN.keys" | awk '{print $2}' | grep -qxF "$pub"; then
    echo "Key already on GitHub"
    return
  fi
  gh auth status --hostname github.com 2>&1 | grep -q admin:public_key ||
    gh auth refresh --hostname github.com --scopes admin:public_key
  gh ssh-key add "$KEY.pub" --title "pllab $(hostname)"
}

linux_user() {
  name=$(printf %s "$LOGIN" | tr '[:upper:]' '[:lower:]')
  case $name in [a-z]*) ;; *) name=gh-$name ;; esac
  echo "${PLLAB_USER:-$name}"
}

write_ssh_config() {
  step "Write the '$ALIAS' entry to $SSH_DIR/config"
  config=$SSH_DIR/config
  touch "$config"
  chmod 600 "$config"
  outside=$(awk -v b="$BEGIN" -v e="$END" '$0==b{skip=1} !skip{print} $0==e{skip=0}' "$config" | awk 'NF{p=1} p')
  if printf '%s\n' "$outside" | grep -Eiq "^[[:space:]]*host[[:space:]].*(^|[[:space:]])$ALIAS([[:space:]]|\$)"; then
    die "$config already has a 'Host $ALIAS' entry. Remove it, or run again with PLLAB_ALIAS=<other name>."
  fi
  known=$SSH_DIR/known_hosts_pllab
  printf '%s\n' "$HOSTKEY" > "$known"
  proxy="ProxyCommand \"$(command -v cloudflared)\" access ssh --hostname %h"
  [ "${PLLAB_PROXY:-}" = none ] && proxy=""
  {
    echo "$BEGIN"
    echo "Host $ALIAS"
    echo "    HostName $HOST"
    [ -n "${PLLAB_PORT:-}" ] && echo "    Port $PLLAB_PORT"
    echo "    User $(linux_user)"
    echo "    IdentityFile \"$KEY\""
    echo "    IdentitiesOnly yes"
    echo "    UserKnownHostsFile \"$known\""
    echo "    StrictHostKeyChecking yes"
    [ -n "$proxy" ] && echo "    $proxy"
    echo "Host *"
    echo "$END"
    echo
    printf '%s\n' "$outside"
  } > "$config.pllab-new"
  cp "$config" "$config.pllab-backup"
  cat "$config.pllab-new" > "$config"
  rm "$config.pllab-new"
}

wait_for_login() {
  step "Connect with 'ssh $ALIAS'"
  i=0
  until ssh -F "$SSH_DIR/config" -o BatchMode=yes -o ConnectTimeout=20 "$ALIAS" true 2>/dev/null; do
    i=$((i + 1))
    [ "$i" -gt 18 ] && die "Login still fails after 3 minutes. Run 'ssh -v $ALIAS' and send the output to a server admin."
    echo "Waiting for the server to create your account ($i/18)"
    sleep 10
  done
  printf '\nDone. Connect with: ssh %s\n' "$ALIAS"
}

install_tools
github_login
join_org
register_key
write_ssh_config
wait_for_login
