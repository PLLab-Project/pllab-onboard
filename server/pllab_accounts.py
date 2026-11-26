#!/usr/bin/python3 -I
"""Keep pllab-server Linux accounts in step with GitHub organization members.

`sync` runs as root from a systemd timer. `keys <user>` runs as the
unprivileged AuthorizedKeysCommandUser and prints the user's GitHub keys.
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

CONFIG_PATH = Path(os.environ.get("PLLAB_ACCOUNTS_CONFIG", "/etc/pllab-accounts/config.json"))
HTTP_TIMEOUT = 4
TOKEN_REUSE_MARGIN = 600
LINUX_NAME_MAX = 32
FIRST_HUMAN_UID = 1000


@dataclass(frozen=True)
class Config:
    org: str
    app_id: int | None
    private_key: Path | None
    group: str
    keys_group: str
    data_dir: Path
    api_base: str
    shell: str
    usernames: dict[str, str]

    @property
    def state_path(self) -> Path:
        return self.data_dir / "accounts.json"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "token.json"

    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"


def load_config(path: Path = CONFIG_PATH) -> Config:
    raw = json.loads(path.read_text())
    key = raw.get("private_key")
    return Config(
        org=raw["org"],
        app_id=raw.get("app_id"),
        private_key=Path(key) if key else None,
        group=raw.get("group", "pllab-members"),
        keys_group=raw.get("keys_group", "pllab-keys"),
        data_dir=Path(raw.get("data_dir", "/opt/pllab-accounts/data")),
        api_base=raw.get("api_base", "https://api.github.com").rstrip("/"),
        shell=raw.get("shell", "/bin/bash"),
        usernames={k.lower(): v for k, v in raw.get("usernames", {}).items()},
    )


class ApiError(Exception):
    def __init__(self, status: int, path: str):
        super().__init__(f"GitHub API {status} for {path}")
        self.status = status


@dataclass
class Response:
    status: int
    body: object
    next_url: str | None


def request(cfg: Config, method: str, path: str, token: str | None, data: dict | None = None) -> Response:
    url = path if path.startswith("http") else cfg.api_base + path
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "pllab-accounts",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            text = resp.read()
            link = resp.headers.get("Link", "")
            return Response(resp.status, json.loads(text) if text else None, _next_link(link))
    except urllib.error.HTTPError as err:
        raise ApiError(err.code, path) from None


def _next_link(link: str) -> str | None:
    match = re.search(r'<([^>]+)>;\s*rel="next"', link)
    return match.group(1) if match else None


def paginate(cfg: Config, path: str, token: str) -> list:
    items: list = []
    url: str | None = path
    while url:
        resp = request(cfg, "GET", url, token)
        items.extend(resp.body)
        url = resp.next_url
    return items


def fresh_token(cfg: Config) -> dict:
    override = os.environ.get("PLLAB_GITHUB_TOKEN")
    if override:
        return {"token": override, "expires_at": time.time() + 3600}
    cached = _read_json(cfg.token_path)
    if cached and cached["expires_at"] - time.time() > TOKEN_REUSE_MARGIN:
        return cached
    if cfg.app_id is None or cfg.private_key is None:
        raise SystemExit("config.json needs app_id and private_key")
    import jwt

    now = int(time.time())
    assertion = jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": str(cfg.app_id)},
        cfg.private_key.read_text(),
        algorithm="RS256",
    )
    installation = request(cfg, "GET", f"/orgs/{cfg.org}/installation", assertion).body
    issued = request(cfg, "POST", f"/app/installations/{installation['id']}/access_tokens", assertion).body
    expires = datetime.fromisoformat(issued["expires_at"].replace("Z", "+00:00")).timestamp()
    return {"token": issued["token"], "expires_at": expires}


# ---- domain -----------------------------------------------------------------

Status = Literal["active", "locked"]


@dataclass
class Account:
    user: str
    login: str
    status: Status


@dataclass
class State:
    accounts: dict[int, Account] = field(default_factory=dict)

    def by_user(self, user: str) -> tuple[int, Account] | None:
        for gid, acct in self.accounts.items():
            if acct.user == user:
                return gid, acct
        return None


@dataclass(frozen=True)
class Create:
    gid: int
    login: str
    user: str


@dataclass(frozen=True)
class Adopt:
    gid: int
    login: str
    user: str


@dataclass(frozen=True)
class Reactivate:
    gid: int
    login: str
    user: str


@dataclass(frozen=True)
class Lock:
    gid: int
    user: str


@dataclass(frozen=True)
class Conflict:
    login: str
    user: str
    reason: str


Action = Create | Adopt | Reactivate | Lock | Conflict


def linux_name(login: str, overrides: dict[str, str]) -> str:
    name = overrides.get(login.lower(), login.lower())
    if not re.match(r"^[a-z]", name):
        name = "gh-" + name
    return name


def plan(state: State, members: dict[int, str], existing: dict[str, int], overrides: dict[str, str]) -> list[Action]:
    """Decide what to change. Pure: no I/O."""
    actions: list[Action] = []
    taken = {acct.user for acct in state.accounts.values()}
    for gid, login in sorted(members.items()):
        acct = state.accounts.get(gid)
        if acct is None:
            user = linux_name(login, overrides)
            adopting = login.lower() in overrides
            if len(user) > LINUX_NAME_MAX or not re.fullmatch(r"[a-z][a-z0-9-]*", user):
                actions.append(Conflict(login, user, "invalid Linux user name; add a usernames override"))
            elif user in taken:
                actions.append(Conflict(login, user, "name already mapped to another GitHub user"))
            elif user in existing and not adopting:
                actions.append(Conflict(login, user, "Linux user exists; add a usernames override to adopt it"))
            elif adopting and user in existing:
                if existing[user] < FIRST_HUMAN_UID:
                    actions.append(Conflict(login, user, "refusing to adopt a system account"))
                    continue
                actions.append(Adopt(gid, login, user))
                taken.add(user)
            else:
                actions.append(Create(gid, login, user))
                taken.add(user)
        elif acct.status == "locked" or acct.user not in existing:
            actions.append(Reactivate(gid, login, acct.user))
    for gid, acct in sorted(state.accounts.items()):
        if gid not in members and acct.status == "active":
            actions.append(Lock(gid, acct.user))
    return actions


def apply(state: State, actions: list[Action], members: dict[int, str]) -> State:
    """Return the state that results from the actions. Pure."""
    accounts = dict(state.accounts)
    for action in actions:
        match action:
            case Create() | Adopt() | Reactivate():
                accounts[action.gid] = Account(action.user, action.login, "active")
            case Lock():
                accounts[action.gid] = Account(action.user, accounts[action.gid].login, "locked")
    for gid, login in members.items():
        if gid in accounts:
            accounts[gid].login = login
    return State(accounts)


# ---- state files --------------------------------------------------------------


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None


def _write_atomic(path: Path, text: str, mode: int, group: str | None = None) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        if group:
            os.chown(tmp, 0, _gid(group))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _gid(group: str) -> int:
    import grp

    return grp.getgrnam(group).gr_gid


def load_state(cfg: Config) -> State:
    raw = _read_json(cfg.state_path) or {"accounts": {}}
    return State({int(gid): Account(**acct) for gid, acct in raw["accounts"].items()})


def save_state(cfg: Config, state: State) -> None:
    raw = {"accounts": {str(gid): vars(acct) for gid, acct in sorted(state.accounts.items())}}
    _write_atomic(cfg.state_path, json.dumps(raw, indent=2) + "\n", 0o644)


# ---- sync (root) --------------------------------------------------------------


def run(*cmd: str, ok: tuple[int, ...] = (0,)) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode not in ok:
        raise RuntimeError(f"{' '.join(cmd)} failed: {result.stderr.strip()}")


def existing_users() -> dict[str, int]:
    return {entry.pw_name: entry.pw_uid for entry in pwd.getpwall()}


def execute(cfg: Config, action: Action) -> None:
    match action:
        case Create(login=login, user=user):
            run("useradd", "--create-home", "--shell", cfg.shell, "--comment", f"GitHub {login}",
                "--user-group", "--groups", cfg.group, "--password", "*", user)
        case Adopt(user=user):
            run("usermod", "--append", "--groups", cfg.group, user)
        case Reactivate(login=login, user=user):
            if user in existing_users():
                run("usermod", "--expiredate", "", "--append", "--groups", cfg.group, user)
            else:
                run("useradd", "--create-home", "--shell", cfg.shell, "--comment", f"GitHub {login}",
                    "--user-group", "--groups", cfg.group, "--password", "*", user)
        case Lock(user=user):
            run("usermod", "--expiredate", "1", user)
            run("gpasswd", "--delete", user, cfg.group, ok=(0, 3))
            run("pkill", "--signal", "KILL", "--uid", user, ok=(0, 1))
            (cfg.keys_dir / user).unlink(missing_ok=True)
        case Conflict(login=login, user=user, reason=reason):
            log(f"skip {login} -> {user}: {reason}")
            return
    log(f"{type(action).__name__.lower()} {action.user}")


def refresh_key_cache(cfg: Config, state: State, token: str) -> None:
    for acct in state.accounts.values():
        if acct.status != "active":
            continue
        try:
            keys = request(cfg, "GET", f"/users/{acct.login}/keys", token).body
        except (ApiError, OSError) as err:
            log(f"keep cached keys for {acct.user}: {err}")
            continue
        text = "".join(k["key"].strip() + "\n" for k in keys)
        _write_atomic(cfg.keys_dir / acct.user, text, 0o644)


def sync(cfg: Config, dry_run: bool) -> int:
    token = fresh_token(cfg)
    members = {m["id"]: m["login"] for m in paginate(cfg, f"/orgs/{cfg.org}/members?per_page=100", token["token"])}
    if not members:
        log("organization member list is empty; refusing to change anything")
        return 1
    state = load_state(cfg)
    actions = plan(state, members, existing_users(), cfg.usernames)
    if dry_run:
        for action in actions:
            print(action)
        return 0
    _write_atomic(cfg.token_path, json.dumps(token), 0o640, cfg.keys_group)
    for action in actions:
        try:
            execute(cfg, action)
        except RuntimeError as err:
            log(str(err))
            continue
        state = apply(state, [action], members)
        save_state(cfg, state)
    state = apply(state, [], members)
    save_state(cfg, state)
    refresh_key_cache(cfg, state, token["token"])
    return 0


# ---- keys (AuthorizedKeysCommand) ------------------------------------------------


def live_keys(cfg: Config, gid: int) -> str | None:
    """Keys for a current member, '' for a non-member, None when GitHub can't be asked."""
    token_file = _read_json(cfg.token_path) or {}
    token = token_file.get("token")
    if not token or token_file.get("expires_at", 0) < time.time():
        return None
    try:
        login = request(cfg, "GET", f"/user/{gid}", token).body["login"]
        try:
            member = request(cfg, "GET", f"/orgs/{cfg.org}/members/{login}", token).status == 204
        except ApiError as err:
            if err.status == 404:
                return ""
            raise
        if not member:
            return ""
        keys = request(cfg, "GET", f"/users/{login}/keys", token).body
    except ApiError as err:
        return "" if err.status == 404 else None
    except OSError:
        return None
    return "".join(k["key"].strip() + "\n" for k in keys)


def keys(cfg: Config, user: str) -> int:
    found = load_state(cfg).by_user(user)
    if not found or found[1].status != "active":
        return 0
    text = live_keys(cfg, found[0])
    if text is None:
        cache = cfg.keys_dir / user
        text = cache.read_text() if cache.exists() else ""
    sys.stdout.write(text)
    return 0


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pllab-accounts")
    sub = parser.add_subparsers(dest="command", required=True)
    sync_cmd = sub.add_parser("sync", help="match Linux accounts to organization members")
    sync_cmd.add_argument("--dry-run", action="store_true")
    keys_cmd = sub.add_parser("keys", help="print authorized keys for a Linux user")
    keys_cmd.add_argument("user")
    args = parser.parse_args(argv)
    cfg = load_config()
    if args.command == "sync":
        return sync(cfg, args.dry_run)
    return keys(cfg, args.user)


if __name__ == "__main__":
    sys.exit(main())
