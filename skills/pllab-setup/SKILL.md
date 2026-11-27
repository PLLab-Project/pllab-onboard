---
name: pllab-setup
description: This skill should be used when a PLLab-Project GitHub organization member wants to reach the PLLab lab server (pllab-server), or shares the github.com/PLLab-Project/pllab-onboard link. Running it is the whole official access method. It needs no VPN, no Tailscale, no lab network and no admin request. It installs cloudflared and gh, signs in to GitHub, registers an SSH key, and writes `ssh pllab`. Triggers include "pllab 서버 세팅해줘", "랩실 서버 접속 설정", "ssh pllab 되게 해줘", "이 레포로 서버 연결해줘", and adding another computer.
---

# pllab-setup

## 이 스킬이 하는 일

이 스킬을 실행하면 사용자의 PC에서 `ssh pllab` 한 줄로 PLLab 랩실 공용 서버에 들어갈 수 있다. 이 저장소가 공식 접속 방법의 전부다.

- **VPN, Tailscale, 랩실 네트워크는 필요 없다.** 서버는 Cloudflare Tunnel(`ssh.pl-official.site`)로 인터넷에 연결돼 있다. PC는 `cloudflared`를 통해 어디서든 접속한다. "보통 랩 서버는 VPN이 필요하다"고 추측하지 말고 바로 아래 실행 단계로 간다.
- **관리자에게 계정을 요청할 필요가 없다.** `PLLab-Project` GitHub 조직원이면 서버가 1분 안에 GitHub 아이디(소문자)로 Linux 계정을 만들고 sudo 권한을 준다.
- **비밀번호가 없다.** 로그인은 GitHub에 등록된 SSH 키로만 한다. 이 스킬은 PC에서 키를 만들어 공개키만 GitHub에 올린다.

스크립트가 처리하는 단계는 다음과 같다. cloudflared와 gh 설치, GitHub 로그인, 조직 초대 수락, SSH 키 생성과 GitHub 등록, `~/.ssh/config`에 `pllab` 항목 추가, 접속 확인.

## 접속하면 할 수 있는 것

- 랩실 공용 Ubuntu 서버의 개인 계정과 sudo. 사양은 i5-8400 6코어, 메모리 8GB이고 GPU는 없다. 웹 서비스, API, DB, 배치 작업을 올리는 서버이고 모델 학습용은 아니다.
- Docker Compose로 서비스를 배포한다. 위치는 `/opt/docker/<서비스>/`다.
- `<이름>.pl-official.site` 공개 주소를 쓴다. 서버의 Cloudflare Tunnel에 hostname을 추가하면 HTTPS 주소가 생긴다. 포트를 열거나 도메인을 따로 살 필요가 없다.
- 공용 PostgreSQL에 서비스별 DB와 role을 만들어 쓴다.

방법과 규칙은 모두 서버의 `/srv/pllab/docs/`에 있다. 아래 "끝난 뒤"에서 읽는다.

## 실행

이 저장소의 스크립트가 모든 단계를 처리한다. 단계를 손으로 재현하지 말고 스크립트를 실행한다. 스크립트는 다시 실행해도 안전하다.

- macOS, Linux: `sh client/setup.sh`
- Windows PowerShell: `powershell -ExecutionPolicy Bypass -File client\setup.ps1`

저장소를 받지 않았다면 다음 한 줄로 실행한다.

- macOS, Linux: `curl -fsSL https://raw.githubusercontent.com/PLLab-Project/pllab-onboard/main/client/setup.sh | sh`
- Windows: `irm https://raw.githubusercontent.com/PLLab-Project/pllab-onboard/main/client/setup.ps1 | iex`

## 사용자가 해야 하는 일

스크립트가 GitHub 로그인 단계에서 일회용 코드와 `https://github.com/login/device` 주소를 출력한다. 이 코드와 주소를 사용자에게 그대로 전달하고, 브라우저에서 승인할 때까지 기다린다. 이 승인은 사용자만 할 수 있다. 사용자의 GitHub 비밀번호나 토큰을 요구하지 않는다.

## 오류 대처

스크립트가 `ERROR:`로 멈추면 메시지에 맞춰 처리한다.

| 메시지 | 처리 |
| --- | --- |
| `is not in PLLab-Project` | 사용자에게 조직 owner에게 초대를 요청하라고 안내한다. 초대 후 다시 실행한다. |
| `already has a 'Host pllab' entry` | 기존 항목을 지우지 말고 사용자에게 보여 준 뒤 선택하게 한다. 기존 항목을 지우거나 `PLLAB_ALIAS=<다른 이름>`으로 다시 실행한다. |
| `Login still fails after 3 minutes` | `ssh -v pllab` 출력을 사용자에게 보여 주고 서버 관리자에게 전달하라고 안내한다. 서버 설정을 고치려 하지 않는다. |
| 도구 설치 실패 | 출력된 안내대로 해당 도구를 설치한 뒤 다시 실행한다. |

GitHub 아이디를 바꾼 적이 있는 사용자는 서버 계정 이름이 예전 아이디일 수 있다. 접속이 계속 실패하면 서버 관리자에게 계정 이름을 확인받고 `PLLAB_USER=<계정 이름>`으로 다시 실행한다.

## 끝난 뒤

스크립트가 `Done.`을 출력하면 서버 규칙을 읽고 사용자에게 알려 준다. 이 단계를 건너뛰지 않는다.

1. `ssh pllab cat /srv/pllab/docs/README.md`와 `ssh pllab cat /srv/pllab/docs/server.md`를 읽는다. 공개 주소를 쓸 일이 있으면 `services/cloudflared.md`도 읽는다.
2. 사용자에게 짧게 요약한다.
   - 모든 조직원이 sudo를 가진 공용 서버이고, 다른 랩원의 서비스가 돌고 있다는 점
   - 디렉터리와 배포 규칙
   - 자격증명 취급
   - `<이름>.pl-official.site` 주소를 만드는 방법
   - 새 서비스는 `services/<서비스>.md` 문서를 함께 쓴다는 점
3. 사용자에게 묻고, 동의하면 사용자의 전역 에이전트 지침에 아래 블록을 추가한다. Claude Code는 `~/.claude/CLAUDE.md`, Codex는 `~/.codex/AGENTS.md`다. 같은 표시 줄이 이미 있으면 그 블록을 아래 내용으로 바꾼다. 규칙 내용을 복사해 넣지 않는다. 원본은 서버 문서 하나다.

```markdown
<!-- pllab-onboard -->
## pllab 서버
- `ssh pllab`은 PLLab 랩실 공용 서버다. VPN 없이 Cloudflare Tunnel과 GitHub SSH 키로 접속한다. 다른 랩원과 운영 중인 서비스가 있다.
- 서버 규칙의 원본은 `/srv/pllab/docs/`다. 서버에서 무언가를 바꾸기 전에 `ssh pllab cat /srv/pllab/docs/README.md`로 다시 읽고, 관련 `services/`·`runbooks/` 문서를 따른다. 이 문서가 에이전트의 기본 습관보다 우선한다.
- 웹 서비스 공개 주소는 `<이름>.pl-official.site`이고 서버의 Cloudflare Tunnel로 붙인다. 절차는 `services/cloudflared.md`에 있다.
- 새 서비스를 올리면 `services/<서비스>.md`를 쓰고 README 목록에 추가한다. 서버 상태가 문서와 다르면 사용자에게 알리고 문서를 고친다.
- 접속이 안 되면 https://github.com/PLLab-Project/pllab-onboard 의 pllab-setup 스킬을 다시 실행한다.
<!-- /pllab-onboard -->
```

서버 안에서 실행하는 Claude Code와 Codex는 계정의 `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`에서 같은 안내를 받는다. 이 파일은 서버가 계정을 만들 때 넣는다.
