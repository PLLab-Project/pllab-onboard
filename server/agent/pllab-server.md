# pllab-server

이 서버는 PLLab 랩실 공용 서버다. 다른 랩원과 운영 중인 서비스가 함께 있고, 모든 조직원이 sudo를 가진다.

이 서버에서 무언가를 바꾸기 전에 `/srv/pllab/docs/README.md`와, 건드리는 대상의 `services/` 또는 `runbooks/` 문서를 읽는다. 경로, 배포, 자격증명, 백업은 이 문서가 원본이며 에이전트 자신의 기본 습관보다 우선한다.

- 웹 서비스 공개 주소는 `<이름>.pl-official.site`다. 서버의 Cloudflare Tunnel에 hostname을 추가해 붙인다. 절차는 `/srv/pllab/docs/services/cloudflared.md`에 있다. 호스트 포트를 외부에 열지 않는다.
- 새 서비스를 올리면 `services/<서비스>.md`를 쓰고 README 목록에 추가한다.
- 서버 상태가 문서와 다르면 사용자에게 알리고 작업의 일부로 문서를 고친다.
