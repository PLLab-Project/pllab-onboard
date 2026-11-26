# 서버 관리자 안내

서버 쪽 구성 요소의 설치, 설정, 운영 절차다. 서버 자체 운영 문서는 서버의 `/srv/pllab/docs/services/pllab-accounts.md`가 원본이다.

## 구성 요소

| 경로 | 역할 |
| --- | --- |
| `/opt/pllab-accounts/bin/pllab-accounts` | `sync`(root, 타이머)와 `keys <user>`(sshd가 `pllab-keys` 계정으로 실행, 캐시만 읽음) |
| `/opt/pllab-accounts/data/accounts.json` | GitHub 사용자 ID와 Linux 계정의 대응, 상태(`active`, `locked`) |
| `/opt/pllab-accounts/data/keys/<user>` | `sync`가 매번 새로 받는 공개키. 24시간보다 오래되면 `keys`가 쓰지 않음 |
| `/etc/pllab-accounts/config.json` | 조직, App ID, 개인키 경로, 계정 이름 예외 |
| `/etc/systemd/system/pllab-accounts.{service,timer}` | 1분마다 `sync` 실행 |
| `/etc/ssh/sshd_config.d/10-pllab-accounts.conf` | `AuthorizedKeysCommand` 연결 |
| `/etc/ssh/sshd_config.d/05-pllab-hardening.conf` | 비밀번호·root 로그인 차단, 터널 출발지 IP를 접속 제한에서 제외 (`--harden`일 때) |
| `/etc/sudoers.d/pllab-members` | `pllab-members` 그룹의 비밀번호 없는 sudo |

## 1. GitHub App 만들기 (조직 owner)

1. 조직 Settings > Developer settings > GitHub Apps > New GitHub App.
2. 이름 `pllab-accounts`, Homepage URL은 이 저장소 주소. Webhook의 Active는 끈다.
3. Permissions > Organization permissions > Members: Read-only. 다른 권한은 주지 않는다.
4. "Only on this account"로 만들고, 만든 뒤 Install App에서 `PLLab-Project`에 설치한다.
5. App ID를 적어 두고 Private keys에서 키를 하나 만든다.

개인키는 서버 자격증명 보관함에 둔다. 값은 Git, 채팅, Obsidian에 남기지 않는다.

```sh
sudo install -d -o root -g pllab-credentials -m 0750 /srv/pllab/credentials/github
sudo install -o root -g pllab-credentials -m 0640 ~/pllab-accounts.pem /srv/pllab/credentials/github/pllab-accounts.pem
rm ~/pllab-accounts.pem
```

## 2. 설치

```sh
git clone https://github.com/PLLab-Project/pllab-onboard.git && cd pllab-onboard
sudo sh server/install.sh
sudoedit /etc/pllab-accounts/config.json   # app_id 입력
sudo /opt/pllab-accounts/bin/pllab-accounts sync --dry-run
sudo sh server/install.sh                  # app_id가 있으면 타이머를 켠다
```

`--dry-run`은 바꿀 내용만 출력한다. 기존 Linux 계정과 이름이 겹치는 조직원은 `skip ... Linux user exists`로 나온다. 같은 사람이면 `usernames`에 `"GitHub 아이디": "기존 계정"`을 넣어 그 계정을 연결한다. UID 1000 미만의 시스템 계정은 연결하지 않는다.

## 3. 키 로그인 확인 후 비밀번호 로그인 끄기

현재 SSH 세션 하나를 열어 둔 채 진행한다.

1. 조직원 한 명이 랩원 절차로 `ssh pllab` 접속에 성공하는지 확인한다.
2. 기존 관리자 계정도 키로 접속되는지 확인한다.
3. `sudo sh server/install.sh --harden`을 실행한다.
4. `sudo sshd -T | grep -E 'passwordauthentication|permitrootlogin'`이 모두 `no`인지 확인한다.
5. 새 세션으로 접속을 다시 확인한 뒤 열어 둔 세션을 닫는다.

키를 모두 잃으면 서버 앞에서 콘솔로 로그인한다. 콘솔 로그인은 비밀번호를 계속 쓴다.

## 4. Cloudflare Access 끄기

Zero Trust > Access > Applications에서 `ssh.pl-official.site`의 앱 `PLLab Server SSH`를 삭제한다. 터널의 `ssh.pl-official.site` 라우팅은 그대로 둔다. 서비스 토큰을 쓰던 기존 PC의 설정은 수정하지 않아도 계속 접속된다.

## 저장소 보호 (조직 owner)

이 저장소는 공개 저장소이고, 랩원의 에이전트와 관리자의 `install.sh`가 main의 스크립트를 그대로 실행한다. main에 push할 수 있는 사람이 곧 모든 랩원 PC와 서버에서 코드를 실행할 수 있는 사람이다.

- main 브랜치 보호를 켜고 PR 리뷰를 필수로 한다.
- 조직의 base repository permission을 `Read`로 둔다. 쓰기 권한은 관리자에게만 준다.
- 조직 설정에서 2FA를 필수로 한다.

## 운영

```sh
systemctl list-timers pllab-accounts.timer
journalctl -u pllab-accounts.service --since today
sudo cat /opt/pllab-accounts/data/accounts.json
```

- 퇴실: 조직에서 빼면 1분 안에 계정이 잠기고 그 계정으로 실행 중인 프로세스가 종료된다. 그 사람이 `sudo`로 띄운 root 프로세스(`sudo tmux` 등)는 남으므로 `ps -ef`로 확인해 정리한다. 홈 디렉터리는 남는다. 완전히 지우려면 `sudo userdel -r <계정>` 후 `accounts.json`에서 그 항목을 지운다.
- 한 번에 활성 계정의 절반 넘게 잠가야 하면 `sync`는 잠금을 건너뛰고 로그를 남긴다. 의도한 변경이면 `sudo /opt/pllab-accounts/bin/pllab-accounts sync --allow-mass-lock`을 실행한다.
- `skip ... -> ...:` 로그는 이름이 겹쳐 계정을 만들지 못한 조직원이다. `config.json`의 `usernames`에 다른 이름을 지정한다.
- `pllab-edge` Docker 네트워크의 대역을 바꾸면 `05-pllab-hardening.conf`의 `PerSourcePenaltyExemptList`도 바꾼다. 그대로 두면 한 사람의 로그인 실패가 터널을 쓰는 모든 접속을 잠시 막는다.
- 복귀: 조직에 다시 넣으면 같은 계정이 다시 열린다.
- GitHub 아이디 변경: Linux 계정 이름은 바뀌지 않는다. 그 사람은 `PLLAB_USER=<기존 계정>`으로 설정 도구를 다시 실행한다.
- 조직원 목록을 받지 못하거나 목록이 비어 있으면 `sync`는 아무것도 바꾸지 않고 실패로 끝난다.
