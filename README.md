# pllab-onboard

PLLab 랩실 서버(`pllab-server`)에 `ssh pllab` 한 줄로 접속하게 해 주는 설정 도구다. `PLLab-Project` GitHub 조직원이면 관리자 승인 없이 쓸 수 있다.

## 랩원: 처음 접속하기

1. `PLLab-Project` 조직 초대를 받는다. 초대 수락은 설정 도구가 대신 처리한다.
2. PC의 코딩 에이전트(Claude Code, Codex 등)에게 이렇게 말한다.

   > https://github.com/PLLab-Project/pllab-onboard 의 pllab-setup 스킬로 pllab 서버 접속을 세팅해줘

   에이전트 없이 직접 실행해도 된다.

   ```sh
   # macOS, Linux
   curl -fsSL https://raw.githubusercontent.com/PLLab-Project/pllab-onboard/main/client/setup.sh | sh
   ```

   ```powershell
   # Windows PowerShell
   irm https://raw.githubusercontent.com/PLLab-Project/pllab-onboard/main/client/setup.ps1 | iex
   ```

3. 중간에 나오는 코드를 브라우저의 GitHub 화면에 입력해 승인한다. 직접 할 일은 이것뿐이다.
4. `Done.`이 나오면 `ssh pllab`으로 접속한다.

다른 PC를 추가할 때도 같은 방법으로 실행한다. PC마다 키가 하나씩 GitHub에 등록된다. PC를 잃어버리면 GitHub 설정의 SSH keys에서 그 PC의 키(`pllab <PC 이름>`)를 지운다. 서버는 1분 안에 그 키를 거부한다. 서버의 `~/.ssh/authorized_keys`에 직접 넣은 키는 GitHub와 상관없이 남으므로 직접 관리한다.

## 동작 방식

- 서버는 1분마다 조직원 목록과 각자의 GitHub 공개키를 읽는다. 새 조직원에게는 GitHub 아이디(소문자)로 Linux 계정을 만들고 sudo 권한을 준다. 조직에서 빠진 사람의 계정은 잠근다. 홈 디렉터리는 남긴다.
- 로그인할 때 서버는 마지막으로 받아 둔 공개키를 쓴다. 로그인이 GitHub를 호출하지 않으므로 GitHub 장애나 반복 로그인 시도가 서버에 영향을 주지 않는다. 받아 둔 키가 24시간보다 오래되면 쓰지 않는다.
- 비밀번호 로그인과 root 로그인은 꺼져 있다. GitHub에 등록한 SSH 키로만 들어온다.
- 설정 도구는 PC에서 키를 만들고 공개키만 GitHub에 올린다. 비밀값을 주고받는 단계가 없어서 이 저장소는 공개 저장소다.

조직 가입이 곧 서버 관리자(sudo) 권한이다. 조직 owner는 초대할 사람을 신중히 고르고, 조직의 2FA 필수 설정을 유지한다.

## 저장소 구성

| 경로 | 내용 |
| --- | --- |
| `client/` | 랩원 PC 설정 스크립트 (`setup.sh`, `setup.ps1`) |
| `skills/pllab-setup/` | 코딩 에이전트용 스킬 |
| `server/` | 서버 동기화와 키 조회 (`pllab_accounts.py`), 설치 스크립트, systemd·sshd 설정 |
| `docs/admin.md` | 서버 관리자용 설치·운영 절차 |
| `tests/` | 단위 테스트와 Docker 종단 테스트 |

## 테스트

```sh
python3 -m unittest discover tests
./tests/e2e.sh   # Docker와 gh 로그인 필요. GitHub에 등록된 ~/.ssh/id_ed25519 사용
```
