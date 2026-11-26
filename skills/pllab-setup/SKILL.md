---
name: pllab-setup
description: Set up `ssh pllab` access to the PLLab lab server (pllab-server) on the user's computer. Use when a PLLab-Project GitHub organization member asks to "pllab 서버 세팅해줘", "랩실 서버 접속 설정", "ssh pllab 되게 해줘", or to add a new computer for the lab server.
---

# pllab-setup

이 스킬은 사용자의 PC에서 `ssh pllab`이 되도록 설정한다. 서버 계정은 서버가 GitHub 조직 가입을 보고 자동으로 만든다. 이 스킬은 PC 쪽만 맡는다.

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

스크립트가 `Done.`을 출력하면 서버 규칙을 읽고 사용자에게 알려 준다.

1. `ssh pllab cat /srv/pllab/docs/README.md`를 실행하고, README가 링크한 `server.md`도 읽는다.
2. 사용자에게 다음을 짧게 요약한다: 디렉터리와 배포 규칙, 자격증명 취급, 서비스별 문서 위치, 모든 조직원이 sudo를 가진 공용 서버라는 점.
3. 사용자에게 묻고, 동의하면 사용자의 전역 에이전트 지침에 아래 블록을 추가한다. Claude Code는 `~/.claude/CLAUDE.md`, Codex는 `~/.codex/AGENTS.md`다. 같은 표시 줄이 이미 있으면 추가하지 않는다. 규칙 내용을 복사해 넣지 않는다. 원본은 서버 문서 하나다.

```markdown
<!-- pllab-onboard -->
## pllab 서버
- `ssh pllab`은 PLLab 랩실 공용 서버다. 다른 랩원과 운영 중인 서비스가 있다.
- 서버에서 무언가를 바꾸기 전에 `ssh pllab cat /srv/pllab/docs/README.md`로 규칙을 다시 읽고, 관련 `services/`·`runbooks/` 문서를 따른다.
- 서버 상태가 문서와 다르면 사용자에게 알리고 작업의 일부로 문서를 고친다.
<!-- /pllab-onboard -->
```

서버 안에서 실행하는 Claude Code와 Codex는 계정의 `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`에서 같은 안내를 받는다. 이 파일은 서버가 계정을 만들 때 넣는다.
