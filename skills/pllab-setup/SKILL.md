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

스크립트가 `Done.`을 출력하면 사용자에게 `ssh pllab`으로 접속하라고 안내한다. 서버 사용법은 접속 후 `/srv/pllab/docs/README.md`에 있다.
