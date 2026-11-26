#!/usr/bin/python3 -I
from __future__ import annotations

import argparse
import grp
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
from pathlib import Path
from typing import Literal

CONFIG_PATH = Path(os.environ.get("PLLAB_ACCOUNTS_CONFIG", "/etc/pllab-accounts/config.json"))
HTTP_TIMEOUT = 10
KEY_CACHE_MAX_AGE = 24 * 3600
LINUX_NAME = re.compile(r"[a-z][a-z0-9-]{0,31}")
HUMAN_UIDS = range(1000, 60000)


@dataclass(frozen=True)
class Config:
    org: str
    app_id: int | None
    private_key: Path | None
    group: str
    data_dir: Path
    api_base: str
    shell: str
    usernames: dict[str, str]

    @property
    def state_path(self) -> Path:
        return self.data_dir / "accounts.json"

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
        data_dir=Path(raw.get("data_dir", "/opt/pllab-accounts/data")),
        api_base=raw.get("api_base", "https://api.github.com").rstrip("/"),
        shell=raw.get("shell", "/bin/bash"),
        usernames={k.lower(): v for k, v in raw.get("usernames", {}).items()},
    )


class ApiError(Exception):
    pass


def request(cfg: Config, method: str, path: str, token: str) -> tuple[object, str | None]:
    url = path if path.startswith("http") else cfg.api_base + path
    req = urllib.request.Request(url, method=method, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "pllab-accounts",
        "Authorization": f"Bearer {token}",
    })
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = json.loads(resp.read() or b"null")
            match = re.search(r'<([^>]+)>;\s*rel="next"', resp.headers.get("Link", ""))
            return body, match.group(1) if match else None
    except urllib.error.HTTPError as err:
        raise ApiError(f"GitHub API {err.code} for {path}") from None
    except (OSError, ValueError) as err:
        raise ApiError(f"GitHub API unreachable for {path}: {err}") from None


def paginate(cfg: Config, path: str, token: str) -> list:
    items: list = []
    url: str | None = path
    while url:
        body, url = request(cfg, "GET", url, token)
        items.extend(body)
    return items


def installation_token(cfg: Config) -> str:
    override = os.environ.get("PLLAB_GITHUB_TOKEN")
    if override:
        return override
    if cfg.app_id is None or cfg.private_key is None:
        raise ApiError("config.json needs app_id and private_key")
    import jwt

    now = int(time.time())
    assertion = jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": str(cfg.app_id)},
        cfg.private_key.read_text(),
        algorithm="RS256",
    )
    installation, _ = request(cfg, "GET", f"/orgs/{cfg.org}/installation", assertion)
    issued, _ = request(cfg, "POST", f"/app/installations/{installation['id']}/access_tokens", assertion)
    return issued["token"]


Status = Literal["active", "locked"]


@dataclass
class Account:
    user: str
    login: str
    status: Status


@dataclass
class State:
    accounts: dict[int, Account] = field(default_factory=dict)

    def active(self, user: str) -> Account | None:
        return next((a for a in self.accounts.values() if a.user == user and a.status == "active"), None)


@dataclass(frozen=True)
class LinuxUser:
    uid: int
    comment: str


@dataclass(frozen=True)
class Host:
    users: dict[str, LinuxUser]
    groups: frozenset[str]


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


def comment_for(login: str) -> str:
    return f"GitHub {login}"


def linux_name(login: str, overrides: dict[str, str]) -> str:
    name = overrides.get(login.lower(), login.lower())
    return name if re.match(r"[a-z]", name) else "gh-" + name


def plan_member(gid: int, login: str, acct: Account | None, host: Host, taken: set[str], overrides: dict[str, str]) -> Action | None:
    if acct is not None:
        existing = host.users.get(acct.user)
        if existing and existing.uid not in HUMAN_UIDS:
            return Conflict(login, acct.user, "mapped name now belongs to a system account")
        if acct.status == "locked" or existing is None:
            return Reactivate(gid, login, acct.user)
        return None
    user = linux_name(login, overrides)
    existing = host.users.get(user)
    if not LINUX_NAME.fullmatch(user):
        return Conflict(login, user, "invalid Linux user name; add a usernames override")
    if user in taken:
        return Conflict(login, user, "name already mapped to another GitHub user")
    if existing is None:
        if user in host.groups:
            return Conflict(login, user, "a group with this name exists; add a usernames override")
        return Create(gid, login, user)
    if existing.uid not in HUMAN_UIDS:
        return Conflict(login, user, "refusing to use a system account")
    if login.lower() in overrides or existing.comment == comment_for(login):
        return Adopt(gid, login, user)
    return Conflict(login, user, "Linux user exists; add a usernames override to adopt it")


def plan(state: State, members: dict[int, str], host: Host, overrides: dict[str, str]) -> list[Action]:
    actions: list[Action] = []
    taken = {acct.user for acct in state.accounts.values()}
    for gid, login in sorted(members.items()):
        action = plan_member(gid, login, state.accounts.get(gid), host, taken, overrides)
        if action is not None:
            actions.append(action)
            taken.add(action.user)
    for gid, acct in sorted(state.accounts.items()):
        if gid not in members and acct.status == "active":
            actions.append(Lock(gid, acct.user))
    return actions


def too_many_locks(state: State, actions: list[Action]) -> bool:
    active = sum(1 for a in state.accounts.values() if a.status == "active")
    locks = sum(1 for a in actions if isinstance(a, Lock))
    return locks > max(2, active // 2)


def apply(state: State, action: Action) -> State:
    accounts = dict(state.accounts)
    match action:
        case Create() | Adopt() | Reactivate():
            accounts[action.gid] = Account(action.user, action.login, "active")
        case Lock():
            accounts[action.gid] = Account(action.user, accounts[action.gid].login, "locked")
    return State(accounts)


def with_logins(state: State, members: dict[int, str]) -> State:
    accounts = {gid: Account(a.user, members.get(gid, a.login), a.status) for gid, a in state.accounts.items()}
    return State(accounts)


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None


def write_atomic(path: Path, text: str, mode: int = 0o644) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_state(cfg: Config) -> State:
    raw = read_json(cfg.state_path) or {"accounts": {}}
    return State({int(gid): Account(**acct) for gid, acct in raw["accounts"].items()})


def save_state(cfg: Config, state: State) -> None:
    raw = {"accounts": {str(gid): vars(acct) for gid, acct in sorted(state.accounts.items())}}
    write_atomic(cfg.state_path, json.dumps(raw, indent=2) + "\n")


def run(*cmd: str, ok: tuple[int, ...] = (0,)) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode not in ok:
        raise RuntimeError(f"{' '.join(cmd)} failed: {result.stderr.strip()}")


def read_host() -> Host:
    users = {e.pw_name: LinuxUser(e.pw_uid, e.pw_gecos) for e in pwd.getpwall()}
    return Host(users, frozenset(g.gr_name for g in grp.getgrall()))


def create_user(cfg: Config, login: str, user: str) -> None:
    run("useradd", "--create-home", "--shell", cfg.shell, "--comment", comment_for(login),
        "--user-group", "--groups", cfg.group, "--password", "*", user)


def execute(cfg: Config, action: Action) -> None:
    match action:
        case Create(login=login, user=user):
            create_user(cfg, login, user)
        case Adopt(user=user):
            run("usermod", "--append", "--groups", cfg.group, user)
        case Reactivate(login=login, user=user):
            if user in read_host().users:
                run("usermod", "--expiredate", "", "--append", "--groups", cfg.group, user)
            else:
                create_user(cfg, login, user)
        case Lock(user=user):
            run("usermod", "--expiredate", "1", user)
            run("gpasswd", "--delete", user, cfg.group, ok=(0, 3))
            run("pkill", "--signal", "KILL", "--uid", user, ok=(0, 1))
            (cfg.keys_dir / user).unlink(missing_ok=True)
        case Conflict(login=login, user=user, reason=reason):
            log(f"skip {login} -> {user}: {reason}")
            return
    log(f"{type(action).__name__.lower()} {action.user}")


def refresh_keys(cfg: Config, state: State, token: str) -> None:
    for acct in state.accounts.values():
        if acct.status != "active":
            continue
        try:
            keys = paginate(cfg, f"/users/{acct.login}/keys?per_page=100", token)
        except ApiError as err:
            log(f"keep cached keys for {acct.user}: {err}")
            continue
        write_atomic(cfg.keys_dir / acct.user, "".join(k["key"].strip() + "\n" for k in keys))


def sync(cfg: Config, dry_run: bool, allow_mass_lock: bool) -> int:
    try:
        token = installation_token(cfg)
        members = {m["id"]: m["login"] for m in paginate(cfg, f"/orgs/{cfg.org}/members?per_page=100", token)}
    except ApiError as err:
        log(f"{err}; nothing changed")
        return 1
    if not members:
        log("organization member list is empty; nothing changed")
        return 1
    state = load_state(cfg)
    actions = plan(state, members, read_host(), cfg.usernames)
    if dry_run:
        for action in actions:
            print(action)
        return 0
    if too_many_locks(state, actions) and not allow_mass_lock:
        log("refusing to lock more than half of the active accounts; rerun with --allow-mass-lock")
        actions = [a for a in actions if not isinstance(a, Lock)]
    for action in actions:
        try:
            execute(cfg, action)
        except RuntimeError as err:
            log(str(err))
            continue
        state = apply(state, action)
        save_state(cfg, state)
    state = with_logins(state, members)
    save_state(cfg, state)
    refresh_keys(cfg, state, token)
    return 0


def keys(cfg: Config, user: str) -> int:
    if not LINUX_NAME.fullmatch(user) or load_state(cfg).active(user) is None:
        return 0
    cache = cfg.keys_dir / user
    try:
        if time.time() - cache.stat().st_mtime < KEY_CACHE_MAX_AGE:
            sys.stdout.write(cache.read_text())
    except FileNotFoundError:
        pass
    return 0


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pllab-accounts")
    sub = parser.add_subparsers(dest="command", required=True)
    sync_cmd = sub.add_parser("sync", help="match Linux accounts to organization members")
    sync_cmd.add_argument("--dry-run", action="store_true")
    sync_cmd.add_argument("--allow-mass-lock", action="store_true")
    keys_cmd = sub.add_parser("keys", help="print authorized keys for a Linux user")
    keys_cmd.add_argument("user")
    args = parser.parse_args(argv)
    cfg = load_config()
    if args.command == "sync":
        return sync(cfg, args.dry_run, args.allow_mass_lock)
    return keys(cfg, args.user)


if __name__ == "__main__":
    sys.exit(main())
